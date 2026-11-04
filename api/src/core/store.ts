import {
  ConditionalCheckFailedException,
  DynamoDBClient,
  PutItemCommand,
  QueryCommand,
  ScanCommand,
  UpdateItemCommand,
  type AttributeValue,
} from '@aws-sdk/client-dynamodb';
import type { Conversation, ConversationStore } from './types.js';

/** Secondary index on producer_id (hash) and created_at (range), serving the list route. */
export const PRODUCER_INDEX = 'producer_id-created_at-index';

type Item = Record<string, AttributeValue>;

const toConversation = (item: Item): Conversation => ({
  conversationId: item.conversation_id!.S!,
  producerId: item.producer_id!.S!,
  createdAt: Number(item.created_at!.N),
  status: item.status!.S as Conversation['status'],
  closedAt: item.closed_at ? Number(item.closed_at.N) : undefined,
  lastActivityAt: Number(item.last_activity_at!.N),
  lockExpiresAt: item.lock_expires_at ? Number(item.lock_expires_at.N) : undefined,
});

const num = (n: number): AttributeValue => ({ N: String(n) });

/** DynamoDB-backed conversations table. Only the chat handlers and the sweep use it. */
export class DynamoConversationStore implements ConversationStore {
  constructor(
    private readonly table: string,
    private readonly client: DynamoDBClient = new DynamoDBClient({}),
  ) {}

  async create(conversation: Conversation): Promise<void> {
    await this.client.send(
      new PutItemCommand({
        TableName: this.table,
        Item: {
          conversation_id: { S: conversation.conversationId },
          producer_id: { S: conversation.producerId },
          created_at: num(conversation.createdAt),
          status: { S: 'open' },
          last_activity_at: num(conversation.lastActivityAt),
        },
        ConditionExpression: 'attribute_not_exists(conversation_id)',
      }),
    );
  }

  async get(conversationId: string): Promise<Conversation | undefined> {
    const out = await this.client.send(
      new QueryCommand({
        TableName: this.table,
        KeyConditionExpression: 'conversation_id = :id',
        ExpressionAttributeValues: { ':id': { S: conversationId } },
        ConsistentRead: true,
        Limit: 1,
      }),
    );
    const item = out.Items?.[0];
    return item ? toConversation(item) : undefined;
  }

  async listByProducer(producerId: string): Promise<Conversation[]> {
    const items: Item[] = [];
    let startKey: Item | undefined;
    do {
      const out = await this.client.send(
        new QueryCommand({
          TableName: this.table,
          IndexName: PRODUCER_INDEX,
          KeyConditionExpression: 'producer_id = :p',
          ExpressionAttributeValues: { ':p': { S: producerId } },
          ScanIndexForward: false,
          ExclusiveStartKey: startKey,
        }),
      );
      items.push(...(out.Items ?? []));
      startKey = out.LastEvaluatedKey;
    } while (startKey);
    return items.map(toConversation);
  }

  async acquireLock(
    conversationId: string,
    now: number,
    lockExpiresAt: number,
    touchActivity: boolean,
  ): Promise<boolean> {
    try {
      await this.client.send(
        new UpdateItemCommand({
          TableName: this.table,
          Key: { conversation_id: { S: conversationId } },
          UpdateExpression: touchActivity
            ? 'SET lock_expires_at = :exp, last_activity_at = :now'
            : 'SET lock_expires_at = :exp',
          ConditionExpression:
            'attribute_exists(conversation_id) AND #status = :open AND ' +
            '(attribute_not_exists(lock_expires_at) OR lock_expires_at < :now)',
          ExpressionAttributeNames: { '#status': 'status' },
          ExpressionAttributeValues: {
            ':exp': num(lockExpiresAt),
            ':now': num(now),
            ':open': { S: 'open' },
          },
        }),
      );
      return true;
    } catch (err) {
      if (err instanceof ConditionalCheckFailedException) return false;
      throw err;
    }
  }

  async releaseLock(conversationId: string): Promise<void> {
    await this.client.send(
      new UpdateItemCommand({
        TableName: this.table,
        Key: { conversation_id: { S: conversationId } },
        UpdateExpression: 'REMOVE lock_expires_at',
      }),
    );
  }

  async markClosed(conversationId: string, now: number): Promise<void> {
    await this.client.send(
      new UpdateItemCommand({
        TableName: this.table,
        Key: { conversation_id: { S: conversationId } },
        UpdateExpression: 'SET #status = :closed, closed_at = :now',
        ExpressionAttributeNames: { '#status': 'status' },
        ExpressionAttributeValues: { ':closed': { S: 'closed' }, ':now': num(now) },
      }),
    );
  }

  async listOpen(): Promise<Conversation[]> {
    const items: Item[] = [];
    let startKey: Item | undefined;
    do {
      const out = await this.client.send(
        new ScanCommand({
          TableName: this.table,
          FilterExpression: '#status = :open',
          ExpressionAttributeNames: { '#status': 'status' },
          ExpressionAttributeValues: { ':open': { S: 'open' } },
          ExclusiveStartKey: startKey,
        }),
      );
      items.push(...(out.Items ?? []));
      startKey = out.LastEvaluatedKey;
    } while (startKey);
    return items.map(toConversation);
  }
}
