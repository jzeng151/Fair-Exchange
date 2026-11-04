import type { AgentRequest, Conversation, Deps } from './types.js';
import { writeErrorThenDone, writeEvent, type Sink } from './stream.js';

export class Conflict extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'Conflict';
  }
}

export class NotFound extends Error {
  constructor() {
    super('Not found');
    this.name = 'NotFound';
  }
}

/** Loads the conversation and checks ownership. A wrong owner looks exactly like a missing ID. */
export async function loadOwned(
  deps: Deps,
  conversationId: string,
  producerId: string,
): Promise<Conversation> {
  const conversation = await deps.store.get(conversationId);
  if (!conversation || conversation.producerId !== producerId) throw new NotFound();
  return conversation;
}

/**
 * Runs one streaming turn against an existing conversation: takes the lock, streams
 * the agent's events through unchanged, closes on `step: closed`, and always releases
 * the lock. A conflicting turn or a closed conversation (for message/action) throws
 * before anything is written, so the handler can map it to a plain status code.
 */
export async function runTurn(
  deps: Deps,
  sink: Sink,
  conversation: Conversation,
  request: AgentRequest,
  options: { requireOpen: boolean },
): Promise<void> {
  if (options.requireOpen && conversation.status === 'closed') {
    throw new Conflict('Conversation is closed');
  }
  const now = deps.now();
  const got = await deps.store.acquireLock(
    conversation.conversationId,
    now,
    now + deps.lockTtlMs,
    /* touchActivity */ request.kind !== 'resume' && request.kind !== 'inactivity_close',
  );
  if (!got) throw new Conflict('A turn is already in progress');

  let doneSent = false;
  try {
    for await (const event of deps.agent.stream(request)) {
      writeEvent(sink, event);
      if (event.type === 'done') doneSent = true;
      if (event.type === 'step' && event.step === 'closed') {
        await deps.store.markClosed(conversation.conversationId, deps.now());
      }
    }
    sink.end();
  } catch {
    deps.log.error('agent stream failed', {
      conversationId: conversation.conversationId,
      producerId: conversation.producerId,
      kind: request.kind,
    });
    if (doneSent) sink.end();
    else writeErrorThenDone(sink, 'agent_failed', 'The agent call failed.');
  } finally {
    await deps.store.releaseLock(conversation.conversationId);
  }
}
