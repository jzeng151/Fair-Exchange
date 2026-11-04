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

/** Glue columns per table. data/tests/test_export.py checks they match fx_data.export.TABLES exactly. */
export const SOURCE_TABLES: Record<string, glue.CfnTable.ColumnProperty[]> = {
  producers: [
    { name: 'producer_id', type: 'string' },
    { name: 'country', type: 'string' },
    { name: 'region', type: 'string' },
    { name: 'crop', type: 'string' },
    { name: 'entity_type', type: 'string' },
    { name: 'supply_chain_role', type: 'string' },
    { name: 'source', type: 'string' },
  ],
  certification: [
    { name: 'producer_id', type: 'string' },
    { name: 'certification_scope', type: 'string' },
  ],
  premium_projects: [
    { name: 'producer_id', type: 'string' },
    { name: 'project_ref', type: 'string' },
    { name: 'source', type: 'string' },
    { name: 'challenge_tag', type: 'string' },
    { name: 'category', type: 'string' },
    { name: 'subcategory', type: 'string' },
    { name: 'name', type: 'string' },
    { name: 'action', type: 'string' },
    { name: 'challenge', type: 'string' },
    { name: 'intended_outcome', type: 'string' },
    { name: 'status', type: 'string' },
    { name: 'start_date', type: 'string' },
    { name: 'end_date', type: 'string' },
  ],
  survey_facts: [
    { name: 'producer_id', type: 'string' },
    { name: 'survey_column', type: 'string' }, // the allowlisted survey column the fact summarizes
    { name: 'text', type: 'string' },
    { name: 'source', type: 'string' },
    { name: 'period', type: 'string' },
    { name: 'responses', type: 'int' },
    { name: 'strength', type: 'string' },
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

    this.databaseName = `${stack.stackName.toLowerCase().replace(/[^a-z0-9_]/g, '_')}_source`;
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
