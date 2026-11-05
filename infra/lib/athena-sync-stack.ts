import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import * as athena from 'aws-cdk-lib/aws-athena';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as glue from 'aws-cdk-lib/aws-glue';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as destinations from 'aws-cdk-lib/aws-lambda-destinations';
import * as eventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as s3 from 'aws-cdk-lib/aws-s3';
import type { Construct } from 'constructs';
import { sourceDatabaseName } from './data-bucket';

/**
 * Spec 28: DynamoDB records table -> S3 objects -> Glue table -> Athena.
 *
 * The records table and its stream belong to the write-back work (spec 26). This stack takes them as inputs,
 * the way the agent spike takes its code location, so `cdk synth` works before that table exists.
 * The Lambda code zip is uploaded by `deploy-athena-sync.sh` (bootstrapless: no CDK assets).
 */
export const SYNC_DATABASE = 'fex';
export const RECORDS_GLUE_TABLE = 'conversation_records';
export const RECORDS_PREFIX = 'records/';
/** Seeded demo records (spec 37): same columns, own prefix and table, never mixed with live records. */
export const SEEDED_GLUE_TABLE = 'records_seeded';
export const SEEDED_PREFIX = 'records-seeded/';

export interface AthenaSyncStackProps extends StackProps {
  recordsTableName: string;
  recordsTableStreamArn: string;
  /** Set when the records table is encrypted with a customer managed key. */
  recordsTableKeyArn?: string;
  codeBucketName: string;
  codeKey: string;
}

const str = 'string';
const citation = `struct<source:${str},standard_clause:${str},period:${str},strength:${str}>`;
const claims = `array<struct<text:${str},citation:${citation}>>`;
const evidence = str; // 'full' | 'limited'

/**
 * Columns mirror the record models (agent/src/fex/models.py); agent/tests/test_glue_columns.py fails if a record
 * field has no column. Timestamps stay strings: the JSON SerDe parses them poorly. Deliberately NOT a column:
 * `pii_matches` (the matched personal words stay in the record for reviewers, not in analytics).
 */
export const RECORD_COLUMNS: { name: string; type: string }[] = [
  { name: 'record_id', type: str },
  { name: 'producer_id', type: str },
  { name: 'version', type: 'int' },
  { name: 'created_at', type: str },
  { name: 'updated_at', type: str },
  { name: 'closed_at', type: str },
  { name: 'consent_history', type: `array<struct<scope:${str},recorded_at:${str}>>` },
  { name: 'ai_usage', type: `array<struct<model_id:${str},input_tokens:bigint,output_tokens:bigint>>` },
  { name: 'source', type: str },
  { name: 'status', type: str },
  { name: 'consent', type: `struct<scope:${str},recorded_at:${str}>` },
  { name: 'language', type: str },
  { name: 'entity_type', type: str },
  { name: 'summary_original', type: str },
  { name: 'summary_english', type: str },
  { name: 'tags', type: `array<${str}>` },
  { name: 'evidence', type: evidence },
  { name: 'earlier_answers',
    type: `array<struct<given_at:${str},reason:${str},insights:${claims},peer_examples:${claims},evidence:${evidence}>>` },
  { name: 'insights', type: claims },
  { name: 'peer_examples', type: claims },
  { name: 'feedback', type: str },
  { name: 'decision_log', type: `array<struct<at:${str},kind:${str},code:${str},refs:array<${str}>>>` },
  { name: 'pii_entity_types', type: `array<${str}>` },
  { name: 'pii_check', type: str },
  { name: 'pii_flag', type: 'boolean' },
  { name: 'pii_review', type: str },
  { name: 'review_status', type: str },
  { name: 'reviewed_by', type: str },
  { name: 'reviewed_at', type: str },
  { name: 'reviewer_tags', type: `array<${str}>` },
  { name: 'reviewer_summary_original', type: str },
  { name: 'reviewer_summary_english', type: str },
];

/**
 * Journey 3: records joined to the producer's Premium, survey and certification data.
 * Scalar columns only, so it also runs on Redshift. The synthetic tables come from #7; the names and the
 * `producer_id` join column below are assumptions to confirm when they land.
 */
/**
 * The producer data tables live in the application stack's source database (infra/lib/data-bucket.ts, #7 #14),
 * filled by deploy.sh. The application stack is `FairExchange` here; a second copy (#40) has its own.
 */
export const SOURCE_DATABASE = sourceDatabaseName('FairExchange');

/**
 * Journey 3: each record with the producer's Premium, survey and certification data. Survey facts are
 * per-question summaries (allowlisted, at least 5 responses each), so the survey figure is the most responses
 * any one question had, not a count of fact rows. Certification is one scope per producer.
 */
export const JOURNEY_3_QUERY = `SELECT
  r.record_id,
  r.producer_id,
  r.status,
  r.consent.scope AS consent_scope,
  r.review_status,
  r.language,
  r.entity_type,
  CASE WHEN r.language = 'en' THEN r.summary_original ELSE r.summary_english END AS summary_english,
  COALESCE(p.premium_projects, 0) AS premium_projects,
  COALESCE(s.survey_responses, 0) AS survey_responses,
  c.certification_scope
FROM ${SYNC_DATABASE}.${RECORDS_GLUE_TABLE} r
LEFT JOIN (SELECT producer_id, COUNT(*) AS premium_projects FROM ${SOURCE_DATABASE}.premium_projects GROUP BY producer_id) p
  ON p.producer_id = r.producer_id
LEFT JOIN (SELECT producer_id, MAX(responses) AS survey_responses FROM ${SOURCE_DATABASE}.survey_facts GROUP BY producer_id) s
  ON s.producer_id = r.producer_id
LEFT JOIN ${SOURCE_DATABASE}.certification c
  ON c.producer_id = r.producer_id`;

/** Athena only: UNNEST of arrays does not port to Redshift the same way. */
export const TAG_COUNTS_QUERY = `SELECT tag, COUNT(*) AS records
FROM ${SYNC_DATABASE}.${RECORDS_GLUE_TABLE}
CROSS JOIN UNNEST(tags) AS t (tag)
WHERE status = 'completed'
GROUP BY tag
ORDER BY records DESC`;

export class AthenaSyncStack extends Stack {
  constructor(scope: Construct, id: string, props: AthenaSyncStackProps) {
    super(scope, id, props);

    const key = new kms.Key(this, 'SyncKey', { enableKeyRotation: true, removalPolicy: RemovalPolicy.RETAIN });
    const privateBucket = (name: string, extra: Partial<s3.BucketProps> = {}) =>
      new s3.Bucket(this, name, {
        encryption: s3.BucketEncryption.KMS,
        encryptionKey: key,
        bucketKeyEnabled: true,
        blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
        enforceSSL: true,
        objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
        removalPolicy: RemovalPolicy.RETAIN,
        ...extra,
      });

    // Separate from the web bucket. Holds one object per record under records/.
    const recordsBucket = privateBucket('RecordsBucket');
    // Failed stream batches are kept here beyond the stream's 24-hour retention.
    const failedBatches = privateBucket('FailedBatchesBucket');
    const athenaResults = privateBucket('AthenaResultsBucket', {
      lifecycleRules: [{ expiration: Duration.days(30) }],
    });

    const table = dynamodb.Table.fromTableAttributes(this, 'RecordsTable', {
      tableName: props.recordsTableName,
      tableStreamArn: props.recordsTableStreamArn,
    });

    const codeBucket = s3.Bucket.fromBucketName(this, 'CodeBucket', props.codeBucketName);
    const syncFunction = new lambda.Function(this, 'SyncFunction', {
      description: 'Spec 28: copies changed records from DynamoDB to S3 for Athena',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'fex_sync.handler.handler',
      code: lambda.Code.fromBucket(codeBucket, props.codeKey),
      timeout: Duration.seconds(60),
      memorySize: 256,
      environment: { RECORDS_TABLE: props.recordsTableName, SYNC_BUCKET: recordsBucket.bucketName },
    });

    // Least privilege: read single items from the records table, and write only the records/ prefix.
    syncFunction.addToRolePolicy(new iam.PolicyStatement({
      sid: 'ReadRecords',
      actions: ['dynamodb:GetItem'],
      resources: [table.tableArn],
    }));
    recordsBucket.grantReadWrite(syncFunction, `${RECORDS_PREFIX}*`);
    recordsBucket.grantDelete(syncFunction, `${RECORDS_PREFIX}*`);
    // head_object on a missing key returns 404 only when the caller may list the bucket
    syncFunction.addToRolePolicy(new iam.PolicyStatement({
      sid: 'ListRecords',
      actions: ['s3:ListBucket'],
      resources: [recordsBucket.bucketArn],
    }));
    if (props.recordsTableKeyArn) {
      kms.Key.fromKeyArn(this, 'RecordsTableKey', props.recordsTableKeyArn).grantDecrypt(syncFunction);
    }

    syncFunction.addEventSource(new eventSources.DynamoEventSource(table, {
      startingPosition: lambda.StartingPosition.TRIM_HORIZON,
      batchSize: 100,
      bisectBatchOnError: true,
      reportBatchItemFailures: true,
      retryAttempts: 5,
      onFailure: new destinations.S3Destination(failedBatches),
    }));

    // Glue database and table, defined here so the shape is reviewed. No crawlers.
    const database = new glue.CfnDatabase(this, 'Database', {
      catalogId: this.account,
      databaseInput: { name: SYNC_DATABASE, description: 'Fair Exchange conversation records' },
    });
    const recordsTable = new glue.CfnTable(this, 'RecordsGlueTable', {
      catalogId: this.account,
      databaseName: SYNC_DATABASE,
      tableInput: {
        name: RECORDS_GLUE_TABLE,
        description: 'Current version of each conversation record (one JSON object per record)',
        tableType: 'EXTERNAL_TABLE',
        parameters: { classification: 'json' },
        storageDescriptor: {
          location: `s3://${recordsBucket.bucketName}/${RECORDS_PREFIX}`,
          columns: RECORD_COLUMNS,
          inputFormat: 'org.apache.hadoop.mapred.TextInputFormat',
          outputFormat: 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat',
          serdeInfo: {
            serializationLibrary: 'org.openx.data.jsonserde.JsonSerDe',
            parameters: { 'ignore.malformed.json': 'false' },
          },
        },
      },
    });
    recordsTable.addDependency(database);

    // Seeded demo records (spec 37): loaded by agent/scripts/load_seeded_records.py; read only by analytics (#29).
    const seededTable = new glue.CfnTable(this, 'SeededRecordsGlueTable', {
      catalogId: this.account,
      databaseName: SYNC_DATABASE,
      tableInput: {
        name: SEEDED_GLUE_TABLE,
        description: 'Seeded demo records (synthetic, spec 37). Never mixed with live records.',
        tableType: 'EXTERNAL_TABLE',
        parameters: { classification: 'json' },
        storageDescriptor: {
          location: `s3://${recordsBucket.bucketName}/${SEEDED_PREFIX}`,
          columns: RECORD_COLUMNS,
          inputFormat: 'org.apache.hadoop.mapred.TextInputFormat',
          outputFormat: 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat',
          serdeInfo: {
            serializationLibrary: 'org.openx.data.jsonserde.JsonSerDe',
            parameters: { 'ignore.malformed.json': 'false' },
          },
        },
      },
    });
    seededTable.addDependency(database);

    const workGroup = new athena.CfnWorkGroup(this, 'WorkGroup', {
      name: 'fex',
      description: 'Fair Exchange analysts',
      recursiveDeleteOption: true,
      workGroupConfiguration: {
        enforceWorkGroupConfiguration: true,
        publishCloudWatchMetricsEnabled: true,
        resultConfiguration: {
          outputLocation: `s3://${athenaResults.bucketName}/results/`,
          encryptionConfiguration: { encryptionOption: 'SSE_KMS', kmsKey: key.keyArn },
        },
      },
    });
    for (const [logicalId, name, description, queryString] of [
      ['Journey3Query', 'journey-3-records-with-premium-survey-certification',
        'Records joined to Premium, survey and certification data. Scalar columns only: runs on Redshift too.',
        JOURNEY_3_QUERY],
      ['TagCountsQuery', 'athena-only-tag-counts',
        'ATHENA ONLY: uses UNNEST, which Redshift does not support the same way.', TAG_COUNTS_QUERY],
    ]) {
      const query = new athena.CfnNamedQuery(this, logicalId, {
        name, description, database: SYNC_DATABASE, workGroup: workGroup.name, queryString,
      });
      query.addDependency(workGroup);
      query.addDependency(recordsTable);
    }

    new CfnOutput(this, 'RecordsBucketName', { value: recordsBucket.bucketName });
    new CfnOutput(this, 'SyncFunctionName', { value: syncFunction.functionName });
    new CfnOutput(this, 'AthenaWorkGroup', { value: 'fex' });
    // For the analytics route (#29) in the FairExchange stack: where Athena writes results, and the key
    new CfnOutput(this, 'AthenaResultsBucketName', { value: athenaResults.bucketName });
    new CfnOutput(this, 'SyncKeyArn', { value: key.keyArn });
  }
}
