import type { APIGatewayProxyEvent } from 'aws-lambda';
import { Unauthorized, type IdentityResolver } from './identity.js';
import { writeEvent, type Sink } from './stream.js';
import { Conflict, NotFound, loadOwned, runTurn } from './turn.js';
import type { Conversation, Deps } from './types.js';
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
export function toErrorResult(err: unknown, deps: Deps, route: string): JsonResult {
  if (err instanceof Unauthorized) return json(401, { message: 'Unauthorized' });
  if (err instanceof BadRequest) return json(400, { message: err.message });
  if (err instanceof NotFound) return json(404, { message: 'Not found' });
  if (err instanceof Conflict) return json(409, { message: err.message });
  deps.log.error('unhandled error', { route });
  return json(500, { message: 'Internal error' });
}

/**
 * A prepared streaming route. `run` writes to the sink and must be called exactly once;
 * everything that can fail with a plain status code has already happened by then.
 */
export interface StreamPlan {
  conversationId?: string;
  run(sink: Sink): Promise<void>;
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

  return {
    conversationId,
    async run(sink) {
      writeEvent(sink, { type: 'conversation', conversationId });
      await runTurn(deps, sink, conversation, { kind: 'start', producerId, conversationId }, {
        requireOpen: true,
      });
    },
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
  return {
    conversationId,
    run: (sink) =>
      runTurn(deps, sink, conversation, { kind: 'message', producerId, conversationId, text }, {
        requireOpen: true,
      }),
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
  return {
    conversationId,
    run: (sink) =>
      runTurn(deps, sink, conversation, { kind: 'action', producerId, conversationId, action }, {
        requireOpen: true,
      }),
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
  const resumed = await deps.agent.resume({ kind: 'resume', producerId, conversationId });
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
