import { CfnOutput, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import type * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

/** The conversations table's index for the list route (api/src/core/store.ts PRODUCER_INDEX). */
export const PRODUCER_INDEX = 'producer_id-created_at-index';

export interface FexTablesProps {
  /** The application data key (docs/specs/05-cdk-stack.md "Security"). */
  encryptionKey: kms.IKey;
}

/**
 * The records and conversations tables (docs/specs/05-cdk-stack.md "Records"). Both use point-in-time
 * recovery, the application data key and on-demand capacity, and are kept when the stack is deleted.
 * No physical names (spec 05): consumers read the names from the stack outputs.
 *
 * Neither table has a TTL attribute: how long records are kept is not decided (#26 "Not decided"), and the
 * conversations table's closing is done by the sweep (#25), not by expiry.
 */
export class FexTables extends Construct {
  /**
   * One item per conversation the producer agreed to store, or declined (#26). Partition key `record_id`
   * (the conversation ID). Streams are keys-only: the Athena sync (#28) uses a change only as a signal and
   * re-reads the item, so no record content is copied into the stream.
   */
  readonly records: dynamodb.Table;
  /**
   * The chat API's conversations and turn lock (#25). Partition key `conversation_id`, and an index on
   * `producer_id` + `created_at` (a number, epoch milliseconds) for the list route. Only the chat handlers and
   * the sweep use it; the agent runtime has no access.
   */
  readonly conversations: dynamodb.Table;

  constructor(scope: Construct, id: string, props: FexTablesProps) {
    super(scope, id);
    const common = {
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: props.encryptionKey,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: RemovalPolicy.RETAIN,
    };

    this.records = new dynamodb.Table(this, 'Records', {
      ...common,
      partitionKey: { name: 'record_id', type: dynamodb.AttributeType.STRING },
      stream: dynamodb.StreamViewType.KEYS_ONLY,
    });

    this.conversations = new dynamodb.Table(this, 'Conversations', {
      ...common,
      partitionKey: { name: 'conversation_id', type: dynamodb.AttributeType.STRING },
    });
    this.conversations.addGlobalSecondaryIndex({
      indexName: PRODUCER_INDEX,
      partitionKey: { name: 'producer_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'created_at', type: dynamodb.AttributeType.NUMBER },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    const stack = Stack.of(this);
    new CfnOutput(stack, 'RecordsTableName', { value: this.records.tableName });
    new CfnOutput(stack, 'RecordsTableArn', { value: this.records.tableArn });
    new CfnOutput(stack, 'RecordsTableStreamArn', { value: this.records.tableStreamArn! });
    new CfnOutput(stack, 'ConversationsTableName', { value: this.conversations.tableName });
    new CfnOutput(stack, 'ConversationsTableArn', { value: this.conversations.tableArn });
  }
}
