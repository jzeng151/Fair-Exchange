import { ConditionalCheckFailedException, DynamoDBClient, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it } from 'vitest';
import { DynamoConversationStore } from './store.js';

const ddb = mockClient(DynamoDBClient);
const store = new DynamoConversationStore('conversations', ddb as unknown as DynamoDBClient);

beforeEach(() => ddb.reset());

describe('DynamoConversationStore turn lock', () => {
  it('takes the lock with a conditional update on an unexpired lock', async () => {
    ddb.on(UpdateItemCommand).resolves({});
    expect(await store.acquireLock('c1', 100, 500, true)).toBe(true);
    const input = ddb.commandCalls(UpdateItemCommand)[0]!.args[0].input;
    expect(input.ConditionExpression).toContain('lock_expires_at < :now');
    expect(input.UpdateExpression).toContain('last_activity_at');
  });

  it('does not touch activity when asked not to (sweep)', async () => {
    ddb.on(UpdateItemCommand).resolves({});
    await store.acquireLock('c1', 100, 500, false);
    expect(ddb.commandCalls(UpdateItemCommand)[0]!.args[0].input.UpdateExpression).not.toContain('last_activity_at');
  });

  it('returns false when the lock is held', async () => {
    ddb.on(UpdateItemCommand).rejects(new ConditionalCheckFailedException({ message: 'held', $metadata: {} }));
    expect(await store.acquireLock('c1', 100, 500, true)).toBe(false);
  });

  it('rethrows other errors', async () => {
    ddb.on(UpdateItemCommand).rejects(new Error('throttled'));
    await expect(store.acquireLock('c1', 100, 500, true)).rejects.toThrow('throttled');
  });
});
