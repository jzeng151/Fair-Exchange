import {
  ConditionalCheckFailedException,
  DynamoDBClient,
  GetItemCommand,
  PutItemCommand,
  ScanCommand,
  type AttributeValue,
} from '@aws-sdk/client-dynamodb';
import { marshall, unmarshall } from '@aws-sdk/util-dynamodb';
import type { ConversationRecord } from '../types/conversation-record.js';

/** A stored record as the review API sees it. Validated against the record schema before every write. */
export type StoredRecord = ConversationRecord & Record<string, unknown>;

/** Thrown when a conditional write fails. Carries the version now stored, if the record still exists. */
export class VersionConflict extends Error {
  constructor(readonly currentVersion: number | undefined) {
    super('Version conflict');
    this.name = 'VersionConflict';
  }
}

export interface RecordStore {
  /** Every closed completed record. Filtering and ordering are the caller's job (a filtered scan, per #27). */
  listClosedCompleted(): Promise<StoredRecord[]>;
  /**
   * Every closed record for one producer, completed or declined (a filtered scan on producer_id, per #32).
   * Ordering and field projection are the caller's job. The producer ID comes only from the identity.
   */
  listClosedByProducer(producerId: string): Promise<StoredRecord[]>;
  /** Strongly consistent read of one record, or undefined. */
  get(recordId: string): Promise<StoredRecord | undefined>;
  /**
   * Replaces the record if the stored version is `expectedVersion`, the conversation is closed and the
   * review is still pending. Throws VersionConflict otherwise.
   */
  replace(record: StoredRecord, expectedVersion: number): Promise<void>;
}

type Item = Record<string, AttributeValue>;

const toRecord = (item: Item): StoredRecord => unmarshall(item) as StoredRecord;

/** DynamoDB-backed records table (#26). Reviewer writes are conditioned on version and closed_at, not producer_id. */
export class DynamoRecordStore implements RecordStore {
  constructor(
    private readonly table: string,
    private readonly client: DynamoDBClient = new DynamoDBClient({}),
  ) {}

  async listClosedCompleted(): Promise<StoredRecord[]> {
    const records: StoredRecord[] = [];
    let startKey: Item | undefined;
    do {
      const out = await this.client.send(
        new ScanCommand({
          TableName: this.table,
          FilterExpression: '#status = :completed AND attribute_type(closed_at, :string)',
          ExpressionAttributeNames: { '#status': 'status' },
          ExpressionAttributeValues: { ':completed': { S: 'completed' }, ':string': { S: 'S' } },
          ExclusiveStartKey: startKey,
        }),
      );
      for (const item of out.Items ?? []) records.push(toRecord(item));
      startKey = out.LastEvaluatedKey;
    } while (startKey);
    return records;
  }

  async listClosedByProducer(producerId: string): Promise<StoredRecord[]> {
    const records: StoredRecord[] = [];
    let startKey: Item | undefined;
    do {
      const out = await this.client.send(
        new ScanCommand({
          TableName: this.table,
          // Closed records for this producer, completed or declined. The producer ID is the caller's,
          // from the identity; a producer can never scan another's records.
          FilterExpression: 'producer_id = :pid AND attribute_type(closed_at, :string)',
          ExpressionAttributeValues: { ':pid': { S: producerId }, ':string': { S: 'S' } },
          ExclusiveStartKey: startKey,
        }),
      );
      for (const item of out.Items ?? []) records.push(toRecord(item));
      startKey = out.LastEvaluatedKey;
    } while (startKey);
    return records;
  }

  async get(recordId: string): Promise<StoredRecord | undefined> {
    const out = await this.client.send(
      new GetItemCommand({ TableName: this.table, Key: { record_id: { S: recordId } }, ConsistentRead: true }),
    );
    return out.Item ? toRecord(out.Item) : undefined;
  }

  async replace(record: StoredRecord, expectedVersion: number): Promise<void> {
    try {
      await this.client.send(
        new PutItemCommand({
          TableName: this.table,
          Item: marshall(record, { removeUndefinedValues: true }),
          ConditionExpression:
            '#version = :expected AND attribute_type(closed_at, :string) AND review_status = :pending',
          ExpressionAttributeNames: { '#version': 'version' },
          ExpressionAttributeValues: {
            ':expected': { N: String(expectedVersion) },
            ':string': { S: 'S' },
            ':pending': { S: 'pending' },
          },
        }),
      );
    } catch (err) {
      if (err instanceof ConditionalCheckFailedException) {
        const current = await this.get(String(record.record_id));
        throw new VersionConflict(typeof current?.version === 'number' ? current.version : undefined);
      }
      throw err;
    }
  }
}
