/**
 * The evaluation stack (spec 36): the six code-based evaluator Lambdas plus the eval data they
 * read — the eval records table and the eval evidence bucket.
 *
 * Eval records never mix with demo or reviewer data (spec 36 US3): the table and bucket belong
 * to this stack alone and are destroyed with the stack (disposable). The evaluators never
 * write — read-only GetItem/GetObject on exactly those two resources.
 *
 * The evaluator code object (one zip bundling eval/src/fx_evals and agent/src/fex — the
 * handlers import fex.models) is built and uploaded by the eval deploy step, which passes the
 * bucket/key and judge model as -c context, same deploy shape as the agent spike (#4).
 * The synthesizer is CDK's default (spec 05): deploy.sh bootstraps the account if needed.
 */
import {
  CfnOutput,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from 'aws-cdk-lib';
import { PolicyStatement, Role, ServicePrincipal } from 'aws-cdk-lib/aws-iam';
import { Architecture, Code, Function, Runtime } from 'aws-cdk-lib/aws-lambda';
import { LogGroup, RetentionDays } from 'aws-cdk-lib/aws-logs';
import { BlockPublicAccess, Bucket, BucketEncryption } from 'aws-cdk-lib/aws-s3';
import {
  AttributeType,
  BillingMode,
  Table,
  TableEncryption,
} from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';
import { Key } from 'aws-cdk-lib/aws-kms';

export interface FairExchangeEvalStackProps extends StackProps {
  /** Bucket with the evaluator zip (built and uploaded by the eval deploy step). */
  codeBucketName: string;
  /** Object key of the evaluator zip. */
  codeKey: string;
  /** KMS key of the code object, when the code bucket is CMK-encrypted. */
  codeKeyArn?: string;
  /** Judge model for the enablement-tone evaluator (the app's large model). */
  judgeModelId: string;
}

const EVALUATORS = [
  'tag_overlap',
  'citation_validity',
  'answer_completeness',
  'directive_language',
  'enablement_tone',
  'scope_leak',
] as const;

// The judge id defaults to AWS-native amazon.nova-pro (no marketplace agreement needed);
// foundation-model ARNs take the bare id, across every US Bedrock region the profile may use.
const US_REGIONS = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2'];

const toTitle = (id: string): string =>
  id.split('_').map((part) => part[0].toUpperCase() + part.slice(1)).join('');

export class FairExchangeEvalStack extends Stack {
  constructor(scope: Construct, id: string, props: FairExchangeEvalStackProps) {
    super(scope, id, props);

    // The eval data key (spec 05: KMS everywhere). Everything here is disposable (spec 36 US3)
    // and dies with the stack, key included.
    const dataKey = new Key(this, 'EvalDataKey', {
      description: 'Fair Exchange eval records/evidence key (disposable)',
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Spec 26's write-back shape: one record per conversation, partition key `record_id`.
    const recordsTable = new Table(this, 'EvalRecordsTable', {
      partitionKey: { name: 'record_id', type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: dataKey,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Spec 34's evidence shape: one capture JSON per conversation ID (object key = the ID).
    const evidenceBucket = new Bucket(this, 'EvalEvidenceBucket', {
      encryption: BucketEncryption.KMS,
      encryptionKey: dataKey,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: false,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const codeBucket = Bucket.fromBucketName(this, 'EvalCodeSource', props.codeBucketName);

    // Read-only store access (the evaluators never write) plus the code object they run from.
    const grantStoreAccess = (role: Role, withJudge: boolean): Role => {
      role.addToPolicy(new PolicyStatement({
        sid: 'ReadEvalRecords',
        actions: ['dynamodb:GetItem'],
        resources: [recordsTable.tableArn],
      }));
      role.addToPolicy(new PolicyStatement({
        sid: 'ReadEvalEvidence',
        actions: ['s3:GetObject'],
        resources: [evidenceBucket.arnForObjects('*')],
      }));
      role.addToPolicy(new PolicyStatement({
        sid: 'DecryptEvalData',
        actions: ['kms:Decrypt'],
        resources: [dataKey.keyArn],
      }));
      role.addToPolicy(new PolicyStatement({
        sid: 'ReadEvalCode',
        actions: ['s3:GetObject'],
        resources: [codeBucket.arnForObjects(props.codeKey)],
      }));
      if (props.codeKeyArn) {
        role.addToPolicy(new PolicyStatement({
          sid: 'DecryptEvalCode',
          actions: ['kms:Decrypt'],
          resources: [props.codeKeyArn],
        }));
      }
      if (withJudge) {
        const foundationId = props.judgeModelId.replace(/^us\./, '');
        const stackRegion = Stack.of(this).region;
        const stackAccount = Stack.of(this).account;
        role.addToPolicy(new PolicyStatement({
          sid: 'InvokeToneJudge',
          actions: [
            'bedrock:Converse',
            'bedrock:InvokeModel',
            'bedrock:InvokeModelWithResponseStream',
          ],
          resources: [
            `arn:aws:bedrock:${stackRegion}:${stackAccount}:inference-profile/${props.judgeModelId}*`,
            ...US_REGIONS.map((region) => `arn:aws:bedrock:${region}::foundation-model/${foundationId}*`),
          ],
        }));
      }
      return role;
    };

    const evaluatorRole = grantStoreAccess(new Role(this, 'EvaluatorRole', {
      assumedBy: new ServicePrincipal('lambda.amazonaws.com'),
      description: 'Fair Exchange eval: the five non-judge evaluators (spec 36)',
    }), false);
    const toneRole = grantStoreAccess(new Role(this, 'ToneEvaluatorRole', {
      assumedBy: new ServicePrincipal('lambda.amazonaws.com'),
      description: 'Fair Exchange eval: enablement-tone evaluator incl. the judge invoke',
    }), true);

    const evaluatorFunction = (evaluatorId: string): Function => {
      const isTone = evaluatorId === 'enablement_tone';
      // An explicit log group (spec 05: every log group has a retention value), wired into the
      // function so Lambda does not create an unmanaged one.
      const logGroup = new LogGroup(this, toTitle(evaluatorId) + 'Logs', {
        retention: RetentionDays.ONE_WEEK,
        removalPolicy: RemovalPolicy.DESTROY,
      });
      return new Function(this, toTitle(evaluatorId) + 'Evaluator', {
        description: `Spec 36 code-based evaluator: ${evaluatorId}`,
        code: Code.fromBucket(codeBucket, props.codeKey),
        runtime: Runtime.PYTHON_3_12,
        architecture: Architecture.ARM_64,
        handler: `fx_evals.lambdas.handler_${evaluatorId}`,
        timeout: Duration.seconds(60),
        memorySize: isTone ? 512 : 256,
        role: isTone ? toneRole : evaluatorRole,
        logGroup,
        environment: {
          EVAL_RECORDS_TABLE: recordsTable.tableName,
          EVAL_EVIDENCE_BUCKET: evidenceBucket.bucketName,
          EVAL_JUDGE_MODEL_ID: props.judgeModelId,
        },
      });
    };

    const functions: Record<string, Function> = {};
    for (const evaluatorId of EVALUATORS) {
      functions[evaluatorId] = evaluatorFunction(evaluatorId);
    }

    new CfnOutput(this, 'RecordsTableName', { value: recordsTable.tableName });
    new CfnOutput(this, 'EvidenceBucketName', { value: evidenceBucket.bucketName });
    new CfnOutput(this, 'EvalDataKeyArn', { value: dataKey.keyArn });
    new CfnOutput(this, 'EvaluatorRoleArn', { value: evaluatorRole.roleArn });
    new CfnOutput(this, 'ToneEvaluatorRoleArn', { value: toneRole.roleArn });
    for (const evaluatorId of EVALUATORS) {
      new CfnOutput(this, toTitle(evaluatorId) + 'EvaluatorArn', {
        value: functions[evaluatorId].functionArn,
        description: `Spec 36 ${evaluatorId} evaluator (code-based)`,
      });
    }
  }
}
