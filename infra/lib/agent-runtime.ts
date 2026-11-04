import { CfnOutput, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import type * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import type * as kms from 'aws-cdk-lib/aws-kms';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import type { FexGuardrail } from './guardrail';
import type { FexMemory } from './memory';

/** The models FEX calls (ADR 0001): US cross-region inference profiles, so processing stays in US regions. */
export const SMALL_MODEL = 'anthropic.claude-haiku-5-5';
export const LARGE_MODEL = 'anthropic.claude-sonnet-5-5';
const US_REGIONS = ['us-east-1', 'us-east-2', 'us-west-2'];

export interface FexRuntimeProps {
  /** Artifacts bucket and the agent code zip's key (a new key per build, so CloudFormation sees a change). */
  codeBucketName: string;
  codeKey: string;
  /** The artifacts bucket's key, to read the code zip. */
  artifactsKeyArn: string;
  /** The application data key: the runtime's log group, the records table and memory use it. */
  dataKey: kms.IKey;
  guardrail: FexGuardrail;
  memory: FexMemory;
  /** Short-term memory event expiry, in days. Must be longer than `maxLifetimeMinutes` (the agent checks). */
  memoryEventExpiryDays: number;
  records: dynamodb.ITable;
  knowledgeBaseId: string;
  knowledgeBaseArn: string;
  /**
   * Maximum conversation lifetime, in minutes (#25, memory spec). Not decided for production: a required
   * deploy-time configuration value with no default.
   */
  maxLifetimeMinutes: number;
  /** Runtime log group retention (spec 05: required deploy-time value, no default). */
  logRetention: logs.RetentionDays;
}

/**
 * The FEX agent on AgentCore Runtime (docs/specs/05-cdk-stack.md "Agent"; ADR 0002 for the deploy pattern).
 * The role is limited to the #13 spec's "Agent runtime permissions"; there is no evidence write (evalAccess).
 *
 * Message content stays out of the logs (ADR 0002 "Turning off content capture"): the OTel setting stops the
 * botocore instrumentation, and the Strands redaction token stops the Strands tracer. Verify after a change
 * by searching the runtime log group for a test sentence.
 */
export class FexRuntime extends Construct {
  readonly runtime: agentcore.CfnRuntime;
  readonly role: iam.Role;
  readonly logGroup: logs.LogGroup;

  constructor(scope: Construct, id: string, props: FexRuntimeProps) {
    super(scope, id);
    const stack = Stack.of(this);
    const { account, region } = stack;
    if (!Object.values(logs.RetentionDays).includes(props.logRetention)) {
      throw new Error(`logRetention must be a CloudWatch Logs retention value in days; got ${props.logRetention}`);
    }
    if (!Number.isInteger(props.maxLifetimeMinutes) || props.maxLifetimeMinutes <= 0) {
      throw new Error(`maxLifetimeMinutes must be a positive whole number; got ${props.maxLifetimeMinutes}`);
    }

    this.role = new iam.Role(this, 'ExecutionRole', {
      assumedBy: new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com', {
        conditions: {
          StringEquals: { 'aws:SourceAccount': account },
          ArnLike: { 'aws:SourceArn': `arn:aws:bedrock-agentcore:${region}:${account}:*` },
        },
      }),
      description: 'Fair Exchange FEX agent: AgentCore Runtime execution role (#13 "Agent runtime permissions")',
    });
    const allow = (sid: string, actions: string[], resources: string[], conditions?: Record<string, unknown>) =>
      this.role.addToPolicy(new iam.PolicyStatement({ sid, actions, resources, conditions }));

    // Models: the two configured US inference profiles and the US-region foundation models behind them
    allow('InvokeConfiguredModels', ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'], [
      ...[SMALL_MODEL, LARGE_MODEL].map((m) => `arn:aws:bedrock:${region}:${account}:inference-profile/us.${m}`),
      ...[SMALL_MODEL, LARGE_MODEL].flatMap((m) => US_REGIONS.map((r) => `arn:aws:bedrock:${r}::foundation-model/${m}`)),
    ]);
    props.guardrail.grantApply(this.role);
    allow('RetrieveStandards', ['bedrock:Retrieve'], [props.knowledgeBaseArn]);
    // Records: the write-back reads and conditionally writes single items (fex.records.DynamoRecordStore)
    allow('RecordsTable', ['dynamodb:GetItem', 'dynamodb:PutItem'], [props.records.tableArn]);
    allow('DataKeyViaDynamoDB', ['kms:Decrypt', 'kms:GenerateDataKey'], [props.dataKey.keyArn],
      { StringEquals: { 'kms:ViaService': `dynamodb.${region}.amazonaws.com` } });
    props.memory.grantAgentAccess(this.role);
    allow('DetectPii', ['comprehend:DetectPiiEntities'], ['*']); // Comprehend has no resource-level permissions
    // Reviewer-facing English summary (#22, changed 2026-11-04): Translate has no resource-level permissions
    allow('TranslateSummary', ['translate:TranslateText'], ['*']);
    allow('ReadAgentCode', ['s3:GetObject'], [`arn:aws:s3:::${props.codeBucketName}/${props.codeKey}`]);
    allow('ArtifactsKeyViaS3', ['kms:Decrypt'], [props.artifactsKeyArn],
      { StringEquals: { 'kms:ViaService': `s3.${region}.amazonaws.com` } });
    // Logs only into the stack's runtime log group (created below, with retention); no CreateLogGroup, so the
    // runtime cannot create one without retention
    allow('RuntimeLogs', ['logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogStreams'],
      [`arn:aws:logs:${region}:${account}:log-group:/aws/bedrock-agentcore/runtimes/*`]);
    allow('DescribeLogGroups', ['logs:DescribeLogGroups'], [`arn:aws:logs:${region}:${account}:log-group:*`]);
    allow('Traces', ['xray:PutTraceSegments', 'xray:PutTelemetryRecords', 'xray:GetSamplingRules',
      'xray:GetSamplingTargets'], ['*']); // X-Ray has no resource-level permissions
    allow('Metrics', ['cloudwatch:PutMetricData'], ['*'], { StringEquals: { 'cloudwatch:namespace': 'bedrock-agentcore' } });
    allow('WorkloadIdentity', ['bedrock-agentcore:GetWorkloadAccessToken',
      'bedrock-agentcore:GetWorkloadAccessTokenForJWT', 'bedrock-agentcore:GetWorkloadAccessTokenForUserId'], [
      `arn:aws:bedrock-agentcore:${region}:${account}:workload-identity-directory/default`,
      `arn:aws:bedrock-agentcore:${region}:${account}:workload-identity-directory/default/workload-identity/*`,
    ]);

    this.runtime = new agentcore.CfnRuntime(this, 'Runtime', {
      agentRuntimeName: `${stack.stackName.replace(/[^A-Za-z0-9]/g, '')}_fex`, // derived from the stack name (spec 05)
      description: 'Fair Exchange FEX conversation agent (#13)',
      roleArn: this.role.roleArn,
      networkConfiguration: { networkMode: 'PUBLIC' },
      protocolConfiguration: 'HTTP',
      agentRuntimeArtifact: {
        codeConfiguration: {
          code: { s3: { bucket: props.codeBucketName, prefix: props.codeKey } },
          entryPoint: ['opentelemetry-instrument', 'main.py'], // ADR 0002: plain main.py emits no traces
          runtime: 'PYTHON_3_12',
        },
      },
      environmentVariables: {
        AWS_REGION: region,
        FEX_SMALL_MODEL: `us.${SMALL_MODEL}`,
        FEX_LARGE_MODEL: `us.${LARGE_MODEL}`,
        FEX_STANDARDS_KB_ID: props.knowledgeBaseId,
        ...props.guardrail.runtimeEnvironment,
        FEX_RECORDS_TABLE: props.records.tableName,
        FEX_MEMORY_ID: props.memory.memoryId,
        FEX_EVENT_EXPIRY_DAYS: String(props.memoryEventExpiryDays),
        FEX_MAX_LIFETIME_MINUTES: String(props.maxLifetimeMinutes),
        // No message content in logs (ADR 0002): the botocore instrumentation reads the first, the Strands
        // tracer the second (an empty unredacted list redacts every content attribute)
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: 'false',
        OTEL_SEMCONV_STABILITY_OPT_IN: 'gen_ai_unredacted_attributes=',
      },
    });
    this.runtime.node.addDependency(this.role);

    // The runtime's log group, with retention and the data key (spec 05 "Log groups"). AgentCore names it after
    // the runtime ID, which exists once the runtime does; the role can't create log groups, so this one is it.
    props.dataKey.addToResourcePolicy(new iam.PolicyStatement({
      sid: 'AllowCloudWatchLogs',
      principals: [new iam.ServicePrincipal(`logs.${region}.amazonaws.com`)],
      actions: ['kms:Encrypt*', 'kms:Decrypt*', 'kms:ReEncrypt*', 'kms:GenerateDataKey*', 'kms:Describe*'],
      resources: ['*'],
      conditions: { ArnLike: { 'kms:EncryptionContext:aws:logs:arn': `arn:aws:logs:${region}:${account}:log-group:*` } },
    }));
    this.logGroup = new logs.LogGroup(this, 'RuntimeLogs', {
      logGroupName: `/aws/bedrock-agentcore/runtimes/${this.runtime.attrAgentRuntimeId}-DEFAULT`,
      retention: props.logRetention,
      encryptionKey: props.dataKey,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    this.logGroup.node.addDependency(props.dataKey);
    // The CloudWatch OTLP logs endpoint writes OpenTelemetry logs to this stream (ADR 0002) and needs it to exist;
    // without it every export fails with 400. The runtime can't create it: the role has no CreateLogGroup.
    new logs.LogStream(this, 'OtelLogStream', {
      logGroup: this.logGroup,
      logStreamName: 'otel-rt-logs',
      removalPolicy: RemovalPolicy.DESTROY,
    });

    new CfnOutput(stack, 'AgentRuntimeArn', { value: this.runtime.attrAgentRuntimeArn });
    new CfnOutput(stack, 'AgentRuntimeId', { value: this.runtime.attrAgentRuntimeId });
    new CfnOutput(stack, 'AgentRuntimeLogGroup', { value: this.logGroup.logGroupName });
  }
}
