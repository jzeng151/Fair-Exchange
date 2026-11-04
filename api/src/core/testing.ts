import type {
  AgentClient,
  AgentEvent,
  AgentRequest,
  Conversation,
  ConversationStore,
  Deps,
  Log,
} from './types.js';
import type { Sink } from './stream.js';
import type { APIGatewayProxyEvent } from 'aws-lambda';

/** Test doubles for the chat handlers. Not imported by deployed code. */

export class MemoryStore implements ConversationStore {
  items = new Map<string, Conversation>();
  async create(c: Conversation) {
    this.items.set(c.conversationId, { ...c });
  }
  async get(id: string) {
    const c = this.items.get(id);
    return c ? { ...c } : undefined;
  }
  async listByProducer(producerId: string) {
    return [...this.items.values()].filter((c) => c.producerId === producerId).map((c) => ({ ...c }));
  }
  async acquireLock(id: string, now: number, exp: number, touch: boolean, token: string) {
    const c = this.items.get(id);
    if (!c || c.status !== 'open') return false;
    // Same condition as DynamoDB: free only when no lock or `lock_expires_at < now`.
    if (c.lockExpiresAt !== undefined && !(c.lockExpiresAt < now)) return false;
    c.lockExpiresAt = exp;
    c.lockToken = token;
    if (touch) c.lastActivityAt = now;
    return true;
  }
  async releaseLock(id: string, token: string) {
    const c = this.items.get(id);
    if (c && c.lockToken === token) {
      delete c.lockExpiresAt;
      delete c.lockToken;
    }
  }
  async markClosed(id: string, now: number) {
    const c = this.items.get(id);
    if (c) {
      c.status = 'closed';
      c.closedAt = now;
    }
  }
  async listOpen() {
    return [...this.items.values()].filter((c) => c.status === 'open').map((c) => ({ ...c }));
  }
}

/** Script entry that never yields again until the call is aborted. */
export const HANG = Symbol('hang');

/** Replays scripted events and records every request it receives. */
export class ScriptedAgent implements AgentClient {
  requests: AgentRequest[] = [];
  /** Events for each stream call, consumed in order. An Error entry is thrown mid-stream. */
  script: Array<Array<AgentEvent | Error | typeof HANG>> = [];
  /** Signals passed to each stream call, in order. */
  signals: Array<AbortSignal | undefined> = [];
  resumeResult: Record<string, unknown> & { step?: string } = { step: 'intake' };
  /** Conversation IDs whose `resume` stalls until aborted. */
  stallResume = new Set<string>();
  /** Called at the start of each stream call (lets tests act "during" a turn). */
  onStream?: () => Promise<void> | void;

  async *stream(request: AgentRequest, signal?: AbortSignal): AsyncGenerator<AgentEvent> {
    this.requests.push(request);
    this.signals.push(signal);
    await this.onStream?.();
    for (const e of this.script.shift() ?? [{ type: 'done' }]) {
      if (e === HANG) {
        // Like a stalled network call: settles only when aborted.
        await new Promise<void>((resolve) => {
          if (signal?.aborted) return resolve();
          signal?.addEventListener('abort', () => resolve());
        });
        throw new Error('aborted');
      }
      if (e instanceof Error) throw e;
      yield e;
    }
  }
  async resume(request: AgentRequest, signal?: AbortSignal) {
    this.requests.push(request);
    this.signals.push(signal);
    if (this.stallResume.has(request.conversationId)) {
      await new Promise<void>((resolve) => {
        if (signal?.aborted) return resolve();
        signal?.addEventListener('abort', () => resolve());
      });
      throw new Error('aborted');
    }
    return this.resumeResult;
  }
}

export class CaptureSink implements Sink {
  chunks: string[] = [];
  ended = false;
  write(chunk: string) {
    this.chunks.push(chunk);
  }
  end() {
    this.ended = true;
  }
  get events(): Array<Record<string, unknown>> {
    return this.chunks.join('').split('\n').filter(Boolean).map((l) => JSON.parse(l));
  }
}

export class CaptureLog implements Log {
  lines: string[] = [];
  info = (m: string, f?: Record<string, unknown>) => void this.lines.push(JSON.stringify([m, f]));
  warn = this.info;
  error = this.info;
}

export function makeDeps(overrides: Partial<Deps> = {}) {
  const store = new MemoryStore();
  const agent = new ScriptedAgent();
  const log = new CaptureLog();
  let n = 0;
  const clock = { t: 1_000_000 };
  const deps: Deps = {
    store,
    agent,
    log,
    now: () => clock.t,
    newId: () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`,
    turnTimeoutMs: 290_000,
    resumeTimeoutMs: 20_000,
    lockTtlMs: 330_000,
    ...overrides,
  };
  return { deps, store, agent, log, clock };
}

export function makeEvent(opts: {
  producerId?: string | null;
  id?: string;
  body?: unknown;
}): APIGatewayProxyEvent {
  return {
    body: opts.body === undefined ? null : typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body),
    pathParameters: opts.id ? { id: opts.id } : null,
    requestContext: {
      authorizer: opts.producerId === null ? undefined : { producerId: opts.producerId ?? 'producer-a' },
    },
  } as unknown as APIGatewayProxyEvent;
}
