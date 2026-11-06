import type { AgentEvent, AgentRequest, Conversation, Deps, ResumeResult } from './types.js';
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

export class TurnTimeout extends Error {
  constructor() {
    super('Turn exceeded its time limit');
    this.name = 'TurnTimeout';
  }
}

/** Proof of holding a conversation's turn lock. Only the holder's token can release it. */
export interface Lease {
  conversationId: string;
  token: string;
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
 * Takes the turn lock for a new turn. Runs during planning, before any response is
 * chosen, so a closed conversation or a busy lock becomes a plain 409.
 *
 * @param touchActivity true for turns a producer started (start, message, action)
 */
export async function beginTurn(
  deps: Deps,
  conversation: Conversation,
  touchActivity: boolean,
): Promise<Lease> {
  if (conversation.status === 'closed') throw new Conflict('Conversation is closed');
  const token = deps.newId();
  const now = deps.now();
  const got = await deps.store.acquireLock(
    conversation.conversationId,
    now,
    now + deps.lockTtlMs,
    touchActivity,
    token,
  );
  if (!got) {
    // The lock update also fails if the conversation closed after it was loaded.
    const fresh = await deps.store.get(conversation.conversationId);
    if (fresh?.status === 'closed') throw new Conflict('Conversation is closed');
    throw new Conflict('A turn is already in progress');
  }
  return { conversationId: conversation.conversationId, token };
}

export const endTurn = (deps: Deps, lease: Lease): Promise<void> =>
  deps.store.releaseLock(lease.conversationId, lease.token);

/**
 * Streams the agent's events, aborting the call once the turn time limit passes.
 * The limit is shorter than the lock lease, so a turn never outlives its lock.
 */
export async function* boundedStream(deps: Deps, request: AgentRequest): AsyncGenerator<AgentEvent> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const expired = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new TurnTimeout());
    }, deps.turnTimeoutMs);
  });
  expired.catch(() => undefined);
  const iterator = deps.agent.stream(request, controller.signal)[Symbol.asyncIterator]();
  try {
    while (true) {
      const next = await Promise.race([iterator.next(), expired]);
      if (next.done) return;
      yield next.value;
    }
  } finally {
    clearTimeout(timer);
    controller.abort();
    // Close the agent stream without waiting on it: a hung stream may never settle.
    void iterator.return?.(undefined)?.catch?.(() => undefined);
  }
}

/**
 * Calls `resume`, aborting it once `resumeTimeoutMs` passes. A stalled call rejects with
 * TurnTimeout instead of blocking the caller (for the sweep, every later conversation).
 */
export async function boundedResume(
  deps: Deps,
  request: { kind: 'resume'; producerId: string; conversationId: string },
): Promise<ResumeResult> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const expired = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new TurnTimeout());
    }, deps.resumeTimeoutMs);
  });
  const call = deps.agent.resume(request, controller.signal);
  // If the deadline wins, the aborted call's rejection must not go unhandled.
  call.catch(() => undefined);
  try {
    return await Promise.race([call, expired]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Runs a turn whose lock is already held: streams the agent's events through unchanged,
 * marks the conversation closed on `step: closed`, and releases the lock with its token.
 * Never throws; failures end the stream with `error` then `done`.
 */
export async function streamTurn(
  deps: Deps,
  sink: Sink,
  conversation: Conversation,
  request: AgentRequest,
  lease: Lease,
): Promise<void> {
  let doneSent = false;
  try {
    for await (const event of boundedStream(deps, request)) {
      if (event.type === 'step' && typeof event.language === 'string' && ['en', 'es', 'fr'].includes(event.language)) {
        if (request.kind === 'start') {
          // The start turn's language comes from the profile, not from anything the producer said, so it is
          // kept apart from `language`: voice still lets Transcribe identify it, while Listen and attachments
          // can use it before the first message (#169).
          if (event.language !== conversation.openingLanguage) {
            await deps.store.setOpeningLanguage?.(conversation.conversationId, lease.token, event.language);
            conversation.openingLanguage = event.language;
          }
        } else if (event.language !== conversation.language) {
          await deps.store.setLanguage?.(conversation.conversationId, lease.token, event.language);
          conversation.language = event.language;
        }
      }
      writeEvent(sink, event);
      if (event.type === 'done') doneSent = true;
      if (event.type === 'step' && event.step === 'closed') {
        await deps.store.markClosed(conversation.conversationId, deps.now());
      }
    }
    sink.end();
  } catch (err) {
    deps.log.error('agent stream failed', {
      conversationId: conversation.conversationId,
      producerId: conversation.producerId,
      kind: request.kind,
      reason: err instanceof TurnTimeout ? 'timeout' : 'error',
    });
    if (doneSent) sink.end();
    else writeErrorThenDone(sink, 'agent_failed', 'The agent call failed.');
  } finally {
    try {
      await endTurn(deps, lease);
    } catch {
      // The lease expiry frees the lock if release fails.
      deps.log.error('lock release failed', { conversationId: conversation.conversationId });
    }
  }
}
