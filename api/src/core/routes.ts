import type { APIGatewayProxyEvent } from 'aws-lambda';
import { Forbidden, Unauthorized, type IdentityResolver } from './identity.js';
import { writeEvent, type Sink } from './stream.js';
import { Conflict, NotFound, beginTurn, boundedResume, endTurn, loadOwned, streamTurn } from './turn.js';
import type { Conversation, Deps, Log } from './types.js';
import {
  BadRequest,
  isConversationId,
  parseActionBody,
  parseMessageBody,
  parseStartBody,
} from './validate.js';

/** Plain (non-streamed) HTTP outcome, used for errors and the GET routes. */
export interface JsonResult {
  statusCode: number;
  body: unknown;
}

export const json = (statusCode: number, body: unknown): JsonResult => ({ statusCode, body });

/** Maps a thrown error to a status code. Anything unexpected becomes a 500 with no detail. */
export function toErrorResult(err: unknown, deps: { log: Log }, route: string): JsonResult {
  if (err instanceof Unauthorized) return json(401, { message: 'Unauthorized' });
  if (err instanceof Forbidden) return json(403, { message: 'Forbidden' });
  if (err instanceof BadRequest) return json(400, { message: err.message });
  if (err instanceof NotFound) return json(404, { message: 'Not found' });
  if (err instanceof Conflict) return json(409, { message: err.message });
  deps.log.error('unhandled error', { route });
  return json(500, { message: 'Internal error' });
}

/**
 * A prepared streaming route. Planning has already done everything that can fail with a
 * plain status code, including taking the turn lock. The caller must then call exactly
 * one of `run` (streams, never throws, releases the lock) or `abandon` (releases the lock).
 */
export interface StreamPlan {
  conversationId: string;
  run(sink: Sink): Promise<void>;
  abandon(): Promise<void>;
}

const pathId = (event: APIGatewayProxyEvent): string => {
  const id = event.pathParameters?.id;
  // A malformed ID cannot exist, so it gets the same 404 as a missing one.
  if (!isConversationId(id)) throw new NotFound();
  return id;
};

/** POST /conversations */
export async function planStart(
  deps: Deps,
  resolve: IdentityResolver,
  event: APIGatewayProxyEvent,
): Promise<StreamPlan> {
  const producerId = await resolve(event);
  parseStartBody(event.body);

  const conversationId = deps.newId();
  const now = deps.now();
  const conversation: Conversation = {
    conversationId,
    producerId,
    createdAt: now,
    status: 'open',
    lastActivityAt: now,
  };
  await deps.store.create(conversation);
  deps.log.info('conversation created', { conversationId, producerId, route: 'start' });
  const lease = await beginTurn(deps, conversation, true);

  return {
    conversationId,
    async run(sink) {
      writeEvent(sink, { type: 'conversation', conversationId });
      await streamTurn(deps, sink, conversation, { kind: 'start', producerId, conversationId }, lease);
    },
    abandon: () => endTurn(deps, lease),
  };
}

/** POST /conversations/{id}/messages */
export async function planMessage(
  deps: Deps,
  resolve: IdentityResolver,
  event: APIGatewayProxyEvent,
): Promise<StreamPlan> {
  const producerId = await resolve(event);
  const conversationId = pathId(event);
  const conversation = await loadOwned(deps, conversationId, producerId);
  const { text } = parseMessageBody(event.body);
  const lease = await beginTurn(deps, conversation, true);
  return {
    conversationId,
    run: (sink) =>
      streamTurn(deps, sink, conversation, { kind: 'message', producerId, conversationId, text }, lease),
    abandon: () => endTurn(deps, lease),
  };
}

/** POST /conversations/{id}/actions */
export async function planAction(
  deps: Deps,
  resolve: IdentityResolver,
  event: APIGatewayProxyEvent,
): Promise<StreamPlan> {
  const producerId = await resolve(event);
  const conversationId = pathId(event);
  const conversation = await loadOwned(deps, conversationId, producerId);
  const action = parseActionBody(event.body);
  const lease = await beginTurn(deps, conversation, true);
  return {
    conversationId,
    run: (sink) =>
      streamTurn(deps, sink, conversation, { kind: 'action', producerId, conversationId, action }, lease),
    abandon: () => endTurn(deps, lease),
  };
}

/** GET /conversations/{id}. Takes no lock and never changes last_activity_at. */
export async function getConversation(
  deps: Deps,
  resolve: IdentityResolver,
  event: APIGatewayProxyEvent,
): Promise<JsonResult> {
  const producerId = await resolve(event);
  const conversationId = pathId(event);
  const conversation = await loadOwned(deps, conversationId, producerId);
  const resumed = await boundedResume(deps, { kind: 'resume', producerId, conversationId });
  return json(200, {
    ...resumed,
    conversationId,
    status: conversation.status,
  });
}

/** GET /conversations. The caller's conversations, newest first. */
export async function listConversations(
  deps: Deps,
  resolve: IdentityResolver,
  event: APIGatewayProxyEvent,
): Promise<JsonResult> {
  const producerId = await resolve(event);
  const items = await deps.store.listByProducer(producerId);
  items.sort((a, b) => b.createdAt - a.createdAt);
  return json(200, {
    conversations: items.map((c) => ({
      conversationId: c.conversationId,
      createdAt: new Date(c.createdAt).toISOString(),
      status: c.status,
    })),
  });
}
