import { DynamoDBClient, GetItemCommand } from '@aws-sdk/client-dynamodb';
import { unmarshall } from '@aws-sdk/util-dynamodb';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { resolveIdentity, requireRole } from './identity.js';
import { isConversationId } from './validate.js';
import { NotFound } from './turn.js';

export interface OwnedConversation {
  id: string;
  status: string;
  /** Identified from the producer's own words. */
  language?: string;
  /** The profile language the conversation opened in, set before the producer writes anything. */
  openingLanguage?: string;
}

/** The language to reply in: the identified one, else the one the conversation opened in. */
export const replyLanguage = (c: OwnedConversation): string | undefined => c.language ?? c.openingLanguage;

/**
 * The ownership check the voice routes use (#25, #41): producer role, a UUID conversation ID from the path,
 * and the stored producer_id must match. Anything else is indistinguishable from a missing conversation.
 */
export async function loadOwnedConversation(db: DynamoDBClient, table: string, event: APIGatewayProxyEvent): Promise<OwnedConversation> {
  const identity = requireRole(await resolveIdentity(event), 'producer');
  const id = event.pathParameters?.id;
  if (!identity.producerId || !isConversationId(id)) throw new NotFound();
  const result = await db.send(new GetItemCommand({ TableName: table, Key: { conversation_id: { S: id } }, ConsistentRead: true }));
  const conversation = result.Item && unmarshall(result.Item);
  if (!conversation || conversation.producer_id !== identity.producerId) throw new NotFound();
  return { id, status: String(conversation.status),
    ...(typeof conversation.language === 'string' ? { language: conversation.language } : {}),
    ...(typeof conversation.opening_language === 'string' ? { openingLanguage: conversation.opening_language } : {}) };
}
