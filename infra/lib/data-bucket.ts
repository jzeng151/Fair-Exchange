import { CfnOutput, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as glue from 'aws-cdk-lib/aws-glue';
import type * as kms from 'aws-cdk-lib/aws-kms';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

/**
 * The data bucket (docs/specs/05-cdk-stack.md "Data"; #7 "Loading"; #14 "Storage"): the producer data as
 * JSON-lines files, one prefix per table, and Glue tables over them for the Journey 3 join in Athena (#28).
 *
 * infra/deploy.sh writes the files with `python -m fx_data.export` and uploads them. Only already-allowlisted
 * data is exported (profiles, Premium projects, survey summary facts, certification scope, the fictional peer
 * catalog); raw survey answers never reach the bucket. The peer catalog has no Glue table: it is for the peer
 * tool, and its private owner_producer_id column is never queried.
 */

/** The source Glue database for a stack: `<stack>_source` (spec 05: names derive from the stack name). */
export const sourceDatabaseName = (stackName: string): string =>
  `${stackName.toLowerCase().replace(/[^a-z0-9_]/g, '_')}_source`;

/** Glue columns per table. data/tests/test_export.py checks they match fx_data.export.TABLES exactly. */
export const SOURCE_TABLES: Record<string, glue.CfnTable.ColumnProperty[]> = {
  producers: [
    { name: 'producer_id', type: 'string' },
    { name: 'country', type: 'string' },
    { name: 'admin1', type: 'string' },
    { name: 'crops', type: 'array<string>' },
    { name: 'entity_type', type: 'string' },
    { name: 'origin', type: 'string' }, // sample or synthetic (#7)
  ],
  certification: [
    { name: 'producer_id', type: 'string' },
    { name: 'certification_scope', type: 'string' },
  ],
  premium_projects: [
    { name: 'project_id', type: 'string' },
    { name: 'producer_id', type: 'string' },
    { name: 'title', type: 'string' },
    { name: 'category', type: 'string' },
    { name: 'sub_category', type: 'string' },
    { name: 'tags', type: 'array<string>' },
    { name: 'start_year', type: 'int' },
    { name: 'amount', type: 'double' },
    { name: 'description', type: 'string' },
  ],
  survey_facts: [
    { name: 'producer_id', type: 'string' },
    { name: 'survey_column', type: 'string' }, // the allowlisted survey column the fact summarizes
    { name: 'text', type: 'string' },
    { name: 'source', type: 'string' },
    { name: 'period', type: 'string' },
    { name: 'responses', type: 'int' },
  ],
};

export interface FexDataBucketProps {
  /** The application data key (docs/specs/05-cdk-stack.md "Security"). */
  encryptionKey: kms.IKey;
}

export class FexDataBucket extends Construct {
  readonly bucket: s3.Bucket;
  /** Glue database name, derived from the stack name (spec 05: no fixed physical names). */
  readonly databaseName: string;

  constructor(scope: Construct, id: string, props: FexDataBucketProps) {
    super(scope, id);
    const stack = Stack.of(this);
    this.bucket = new s3.Bucket(this, 'Bucket', {
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: props.encryptionKey,
      bucketKeyEnabled: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    this.databaseName = sourceDatabaseName(stack.stackName);
    const database = new glue.CfnDatabase(this, 'Database', {
      catalogId: stack.account,
      databaseInput: { name: this.databaseName, description: 'Fair Exchange producer data (data bucket, #7 #14)' },
    });
    for (const [table, columns] of Object.entries(SOURCE_TABLES)) {
      const glueTable = new glue.CfnTable(this, `Table_${table}`, {
        catalogId: stack.account,
        databaseName: this.databaseName,
        tableInput: {
          name: table,
          tableType: 'EXTERNAL_TABLE',
          parameters: { classification: 'json' },
          storageDescriptor: {
            columns,
            location: `s3://${this.bucket.bucketName}/${table}/`,
            inputFormat: 'org.apache.hadoop.mapred.TextInputFormat',
            outputFormat: 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat',
            serdeInfo: {
              serializationLibrary: 'org.openx.data.jsonserde.JsonSerDe',
              parameters: { 'ignore.malformed.json': 'false' },
            },
          },
        },
      });
      glueTable.addDependency(database);
    }

    new CfnOutput(stack, 'DataBucketName', { value: this.bucket.bucketName });
    new CfnOutput(stack, 'DataGlueDatabase', { value: this.databaseName });
  }
}
