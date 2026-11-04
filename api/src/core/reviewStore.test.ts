import {
  ConditionalCheckFailedException,
  DynamoDBClient,
  GetItemCommand,
  PutItemCommand,
  ScanCommand,
} from '@aws-sdk/client-dynamodb';
import { marshall } from '@aws-sdk/util-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it } from 'vitest';
import { DynamoRecordStore, VersionConflict, type StoredRecord } from './reviewStore.js';

const ddb = mockClient(DynamoDBClient);
const store = new DynamoRecordStore('records', ddb as unknown as DynamoDBClient);
const rec = (over: Record<string, unknown> = {}) =>
  ({ record_id: 'r1', status: 'completed', version: 3, closed_at: '2026-11-04T10:30:00Z', review_status: 'pending', ...over }) as StoredRecord;

beforeEach(() => ddb.reset());

describe('DynamoRecordStore', () => {
  it('scans for closed completed records across pages and unmarshalls plain values', async () => {
    ddb
      .on(ScanCommand)
      .resolvesOnce({ Items: [marshall(rec({ record_id: 'a' }))], LastEvaluatedKey: { record_id: { S: 'a' } } })
      .resolvesOnce({ Items: [marshall(rec({ record_id: 'b' }))] });
    const records = await store.listClosedCompleted();
    expect(records.map((r) => r.record_id)).toEqual(['a', 'b']);
    expect(records[0]!.version).toBe(3); // a number, not {N: "3"}
    const first = ddb.commandCalls(ScanCommand)[0]!.args[0].input;
    expect(first.FilterExpression).toContain("#status = :completed");
    expect(first.FilterExpression).toContain('attribute_type(closed_at');
    expect(ddb.commandCalls(ScanCommand)[1]!.args[0].input.ExclusiveStartKey).toEqual({ record_id: { S: 'a' } });
  });

  it('scans a producer’s closed records (completed and declined) across pages, filtered on producer_id', async () => {
    ddb
      .on(ScanCommand)
      .resolvesOnce({
        Items: [marshall(rec({ record_id: 'a', producer_id: 'producer-a' }))],
        LastEvaluatedKey: { record_id: { S: 'a' } },
      })
      .resolvesOnce({ Items: [marshall(rec({ record_id: 'b', producer_id: 'producer-a', status: 'declined' }))] });
    const records = await store.listClosedByProducer('producer-a');
    expect(records.map((r) => r.record_id)).toEqual(['a', 'b']);
    const first = ddb.commandCalls(ScanCommand)[0]!.args[0].input;
    expect(first.FilterExpression).toContain('producer_id = :pid');
    expect(first.FilterExpression).toContain('attribute_type(closed_at');
    expect(first.FilterExpression).not.toContain('#status'); // both completed and declined are returned
    expect(first.ExpressionAttributeValues![':pid']).toEqual({ S: 'producer-a' });
    expect(ddb.commandCalls(ScanCommand)[1]!.args[0].input.ExclusiveStartKey).toEqual({ record_id: { S: 'a' } });
  });

  it('reads one record with a strongly consistent read', async () => {
    ddb.on(GetItemCommand).resolves({ Item: marshall(rec()) });
    expect((await store.get('r1'))?.record_id).toBe('r1');
    const input = ddb.commandCalls(GetItemCommand)[0]!.args[0].input;
    expect(input).toMatchObject({ Key: { record_id: { S: 'r1' } }, ConsistentRead: true });
  });

  it('returns undefined for a missing record', async () => {
    ddb.on(GetItemCommand).resolves({});
    expect(await store.get('nope')).toBeUndefined();
  });

  it('conditions a replace on version, closed_at and a pending review, never on producer_id', async () => {
    ddb.on(PutItemCommand).resolves({});
    await store.replace(rec({ version: 4 }), 3);
    const input = ddb.commandCalls(PutItemCommand)[0]!.args[0].input;
    expect(input.ConditionExpression).toContain('#version = :expected');
    expect(input.ConditionExpression).toContain('attribute_type(closed_at');
    expect(input.ConditionExpression).toContain('review_status = :pending');
    expect(input.ConditionExpression).not.toContain('producer_id');
    expect(input.ExpressionAttributeValues![':expected']).toEqual({ N: '3' });
  });

  it('turns a failed condition into a VersionConflict carrying the stored version', async () => {
    ddb.on(PutItemCommand).rejects(new ConditionalCheckFailedException({ message: 'no', $metadata: {} }));
    ddb.on(GetItemCommand).resolves({ Item: marshall(rec({ version: 5 })) });
    await expect(store.replace(rec({ version: 4 }), 3)).rejects.toMatchObject({
      name: 'VersionConflict',
      currentVersion: 5,
    });
    await expect(store.replace(rec({ version: 4 }), 3)).rejects.toBeInstanceOf(VersionConflict);
  });
});
