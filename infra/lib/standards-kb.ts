import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { CfnOutput, CustomResource, Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3vectors from 'aws-cdk-lib/aws-s3vectors';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import { CLAUSE_DOCS_PREFIX } from './artifacts-stack';

const EMBEDDING_MODEL = 'amazon.titan-embed-text-v2:0';
const DIMENSIONS = 1024;
const INGEST_LIMIT = Duration.minutes(20);

export interface StandardsKnowledgeBaseProps {
  /** Artifacts bucket (FairExchangeArtifacts) holding the clause documents under `clauses/`. */
  artifactsBucketName: string;
  /** Customer-managed data key (FairExchangeArtifacts): artifacts bucket and vector bucket encryption. */
  dataKeyArn: string;
  /** SHA-256 of the clause documents (fx_data.standards_kb). A new hash re-ingests on deploy. */
  contentHash: string;
}

/**
 * Standards grounding (#17, docs/specs/17-standards-grounding.md): a Bedrock Knowledge Base with an S3
 * Vectors store (KMS-encrypted), Titan Text Embeddings V2 and one document per clause (no chunking), plus a
 * custom resource that ingests the documents during deploy. Ingestion failure, any failed document, or more
 * than 20 minutes fails the deploy. Delete removes the Knowledge Base and its vectors; the custom resource
 * itself does nothing on delete.
 *
 * The ingestion handler is inline Lambda code plus a Step Functions poll loop: no CDK assets (bootstrapless
 * synthesizer) and no 15-minute Lambda limit on the wait.
 */
export class StandardsKnowledgeBase extends Construct {
  readonly knowledgeBaseId: string;
  readonly knowledgeBaseArn: string;

  constructor(scope: Construct, id: string, props: StandardsKnowledgeBaseProps) {
    super(scope, id);
    const stack = Stack.of(this);
    const { region, account } = stack;
    const docsArn = `arn:aws:s3:::${props.artifactsBucketName}`;

    // ---------------------------------------------------------------- vector store
    const vectorBucket = new s3vectors.CfnVectorBucket(this, 'VectorBucket', {
      encryptionConfiguration: { sseType: 'aws:kms', kmsKeyArn: props.dataKeyArn },
    });
    const index = new s3vectors.CfnIndex(this, 'ClauseIndex', {
      vectorBucketArn: vectorBucket.attrVectorBucketArn,
      indexName: 'clauses',
      dataType: 'float32',
      dimension: DIMENSIONS,
      distanceMetric: 'cosine',
      // Bedrock stores chunk text and its own metadata on each vector; keep them out of the filterable
      // metadata size limit (spike check in the #17 spec, per the Bedrock chunking docs)
      metadataConfiguration: { nonFilterableMetadataKeys: ['AMAZON_BEDROCK_TEXT', 'AMAZON_BEDROCK_METADATA'] },
    });

    // ---------------------------------------------------------------- knowledge base
    const embeddingModelArn = `arn:aws:bedrock:${region}::foundation-model/${EMBEDDING_MODEL}`;
    const kbRole = new iam.Role(this, 'KnowledgeBaseRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: {
          StringEquals: { 'aws:SourceAccount': account },
          ArnLike: { 'aws:SourceArn': `arn:aws:bedrock:${region}:${account}:knowledge-base/*` },
        },
      }),
      inlinePolicies: {
        KnowledgeBase: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({ actions: ['bedrock:InvokeModel'], resources: [embeddingModelArn] }),
            new iam.PolicyStatement({ actions: ['s3:GetObject'], resources: [`${docsArn}/${CLAUSE_DOCS_PREFIX}*`] }),
            new iam.PolicyStatement({
              actions: ['s3:ListBucket'], resources: [docsArn],
              conditions: { StringLike: { 's3:prefix': [`${CLAUSE_DOCS_PREFIX}*`] } },
            }),
            new iam.PolicyStatement({
              actions: ['s3vectors:PutVectors', 's3vectors:GetVectors', 's3vectors:DeleteVectors',
                's3vectors:QueryVectors', 's3vectors:GetIndex'],
              resources: [index.attrIndexArn],
            }),
            // The data key, only through S3 (reading documents) and S3 Vectors (writing and querying vectors)
            new iam.PolicyStatement({
              actions: ['kms:Decrypt', 'kms:GenerateDataKey'], resources: [props.dataKeyArn],
              conditions: { StringEquals: { 'kms:ViaService': [`s3.${region}.amazonaws.com`, `s3vectors.${region}.amazonaws.com`] } },
            }),
          ],
        }),
      },
    });

    const knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'KnowledgeBase', {
      name: `${stack.stackName}-standards`,
      description: 'Fair Trade USA APS and FPS clauses, one document per clause (issue #17)',
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn,
          embeddingModelConfiguration: {
            bedrockEmbeddingModelConfiguration: { dimensions: DIMENSIONS, embeddingDataType: 'FLOAT32' },
          },
        },
      },
      storageConfiguration: {
        type: 'S3_VECTORS',
        s3VectorsConfiguration: { indexArn: index.attrIndexArn, vectorBucketArn: vectorBucket.attrVectorBucketArn },
      },
    });
    this.knowledgeBaseId = knowledgeBase.attrKnowledgeBaseId;
    this.knowledgeBaseArn = knowledgeBase.attrKnowledgeBaseArn;

    const dataSource = new bedrock.CfnDataSource(this, 'ClauseDocuments', {
      knowledgeBaseId: this.knowledgeBaseId,
      name: 'clauses',
      dataDeletionPolicy: 'DELETE',
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: { bucketArn: docsArn, inclusionPrefixes: [CLAUSE_DOCS_PREFIX] },
      },
      // One chunk per clause document, so the top 5 results are 5 distinct clauses
      vectorIngestionConfiguration: { chunkingConfiguration: { chunkingStrategy: 'NONE' } },
    });

    // ---------------------------------------------------------------- ingestion during deploy
    const stateMachineName = `${stack.stackName}-StandardsIngest`;
    const stateMachineArn = `arn:aws:states:${region}:${account}:stateMachine:${stateMachineName}`;
    const code = readFileSync(join(__dirname, 'standards-kb', 'ingest_handler.py'), 'utf8');
    if (code.length > 4096) throw new Error('ingest_handler.py must stay under 4 KB to be inlined');

    const ingestFn = new lambda.Function(this, 'IngestHandler', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'index.handler',
      code: lambda.Code.fromInline(code),
      timeout: Duration.minutes(1),
      environment: { STATE_MACHINE_ARN: stateMachineArn, LIMIT_SECONDS: String(INGEST_LIMIT.toSeconds()) },
      logGroup: new logs.LogGroup(this, 'IngestHandlerLogs', {
        retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
    });
    ingestFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:StartIngestionJob', 'bedrock:GetIngestionJob', 'bedrock:StopIngestionJob'],
      resources: [this.knowledgeBaseArn],
    }));
    ingestFn.addToRolePolicy(new iam.PolicyStatement({ actions: ['states:StartExecution'], resources: [stateMachineArn] }));

    const poll = new tasks.LambdaInvoke(this, 'CheckIngestion', { lambdaFunction: ingestFn, payloadResponseOnly: true });
    const reportFailure = new tasks.LambdaInvoke(this, 'ReportFailure', { lambdaFunction: ingestFn, payloadResponseOnly: true })
      .next(new sfn.Fail(this, 'IngestionFailed'));
    poll.addCatch(reportFailure, { resultPath: '$.error' });
    const wait = new sfn.Wait(this, 'WaitForIngestion', { time: sfn.WaitTime.duration(Duration.seconds(20)) });
    const finished = new sfn.Choice(this, 'Finished?')
      .when(sfn.Condition.booleanEquals('$.done', true), new sfn.Succeed(this, 'Reported'))
      .otherwise(wait);
    wait.next(poll).next(finished);

    const stateMachine = new sfn.StateMachine(this, 'IngestStateMachine', {
      stateMachineName,
      definitionBody: sfn.DefinitionBody.fromChainable(wait),
      timeout: INGEST_LIMIT.plus(Duration.minutes(5)), // the Lambda answers CloudFormation at 20 minutes
    });

    const ingest = new CustomResource(this, 'IngestClauses', {
      serviceToken: ingestFn.functionArn,
      serviceTimeout: INGEST_LIMIT.plus(Duration.minutes(10)),
      properties: {
        KnowledgeBaseId: this.knowledgeBaseId,
        DataSourceId: dataSource.attrDataSourceId,
        ContentHash: props.contentHash,
      },
    });
    ingest.node.addDependency(stateMachine);

    new CfnOutput(stack, 'StandardsKnowledgeBaseId', { value: this.knowledgeBaseId });
    new CfnOutput(stack, 'StandardsKnowledgeBaseArn', { value: this.knowledgeBaseArn });
  }
}
