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
  async acquireLock(id: string, now: number, exp: number, touch: boolean) {
    const c = this.items.get(id);
    if (!c || c.status !== 'open') return false;
    if (c.lockExpiresAt !== undefined && c.lockExpiresAt >= now) return false;
    c.lockExpiresAt = exp;
    if (touch) c.lastActivityAt = now;
    return true;
  }
  async releaseLock(id: string) {
    const c = this.items.get(id);
    if (c) delete c.lockExpiresAt;
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

/** Replays scripted events and records every request it receives. */
export class ScriptedAgent implements AgentClient {
  requests: AgentRequest[] = [];
  /** Events for each stream call, consumed in order. An Error entry is thrown mid-stream. */
  script: Array<Array<AgentEvent | Error>> = [];
  resumeResult: Record<string, unknown> & { step?: string } = { step: 'intake' };
  /** Called at the start of each stream call (lets tests act "during" a turn). */
  onStream?: () => Promise<void> | void;

  async *stream(request: AgentRequest): AsyncGenerator<AgentEvent> {
    this.requests.push(request);
    await this.onStream?.();
    for (const e of this.script.shift() ?? [{ type: 'done' }]) {
      if (e instanceof Error) throw e;
      yield e;
    }
  }
  async resume(request: AgentRequest) {
    this.requests.push(request);
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
