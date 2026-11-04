import { ConditionalCheckFailedException, DynamoDBClient, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it } from 'vitest';
import { DynamoConversationStore } from './store.js';

const ddb = mockClient(DynamoDBClient);
const store = new DynamoConversationStore('conversations', ddb as unknown as DynamoDBClient);
const held = () => new ConditionalCheckFailedException({ message: 'held', $metadata: {} });

beforeEach(() => ddb.reset());

describe('DynamoConversationStore turn lock', () => {
  it('takes the lock with a conditional update and records the holder token', async () => {
    ddb.on(UpdateItemCommand).resolves({});
    expect(await store.acquireLock('c1', 100, 500, true, 'tok-1')).toBe(true);
    const input = ddb.commandCalls(UpdateItemCommand)[0]!.args[0].input;
    expect(input.ConditionExpression).toContain('lock_expires_at < :now');
    expect(input.ConditionExpression).toContain('#status = :open');
    expect(input.UpdateExpression).toContain('lock_token = :token');
    expect(input.UpdateExpression).toContain('last_activity_at');
    expect(input.ExpressionAttributeValues?.[':token']).toEqual({ S: 'tok-1' });
  });

  it('does not touch activity when asked not to (sweep)', async () => {
    ddb.on(UpdateItemCommand).resolves({});
    await store.acquireLock('c1', 100, 500, false, 'tok-1');
    expect(ddb.commandCalls(UpdateItemCommand)[0]!.args[0].input.UpdateExpression).not.toContain('last_activity_at');
  });

  it('returns false when the lock is held', async () => {
    ddb.on(UpdateItemCommand).rejects(held());
    expect(await store.acquireLock('c1', 100, 500, true, 'tok-1')).toBe(false);
  });

  it('rethrows other errors', async () => {
    ddb.on(UpdateItemCommand).rejects(new Error('throttled'));
    await expect(store.acquireLock('c1', 100, 500, true, 'tok-1')).rejects.toThrow('throttled');
  });

  it('releases only when the token still holds the lock', async () => {
    ddb.on(UpdateItemCommand).resolves({});
    await store.releaseLock('c1', 'tok-1');
    const input = ddb.commandCalls(UpdateItemCommand)[0]!.args[0].input;
    expect(input.ConditionExpression).toBe('lock_token = :token');
    expect(input.ExpressionAttributeValues?.[':token']).toEqual({ S: 'tok-1' });
  });

  it("ignores a release after another turn took the lock", async () => {
    ddb.on(UpdateItemCommand).rejects(held());
    await expect(store.releaseLock('c1', 'stale')).resolves.toBeUndefined();
  });
});
