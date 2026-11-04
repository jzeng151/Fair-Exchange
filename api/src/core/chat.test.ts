import { describe, expect, it } from 'vitest';
import { resolveCaller, type IdentityResolver } from './identity.js';
import {
  getConversation,
  listConversations,
  planAction,
  planMessage,
  planStart,
  toErrorResult,
  type JsonResult,
  type StreamPlan,
} from './routes.js';
import { runSweep } from './sweep.js';
import { CaptureSink, HANG, makeDeps, makeEvent } from './testing.js';

/** Fake resolver (#11 spec): returns the producer the test event carries in its authorizer. */
const resolve: IdentityResolver = resolveCaller;

const CONV_B = '00000000-0000-4000-8000-0000000000bb';

async function startConversation(t: ReturnType<typeof makeDeps>, producerId = 'producer-a') {
  const plan = await planStart(t.deps, resolve, makeEvent({ producerId }));
  const sink = new CaptureSink();
  await plan.run(sink);
  return { id: plan.conversationId!, sink };
}

/**
 * Mirrors the Lambda handler: only planning errors become status codes. Once a plan
 * exists the 200 stream is open, so `run` must never throw (the test fails if it does).
 */
async function call(
  t: ReturnType<typeof makeDeps>,
  fn: () => Promise<StreamPlan>,
): Promise<{ result?: JsonResult; sink: CaptureSink }> {
  const sink = new CaptureSink();
  let plan: StreamPlan;
  try {
    plan = await fn();
  } catch (err) {
    return { result: toErrorResult(err, t.deps, 'test'), sink };
  }
  await plan.run(sink);
  return { sink };
}

describe('identity', () => {
  it('returns 401 on every route when the caller cannot be resolved', async () => {
    const t = makeDeps();
    const e = makeEvent({ producerId: null, id: CONV_B, body: { text: 'hi' } });
    for (const fn of [
      () => planStart(t.deps, resolve, e),
      () => planMessage(t.deps, resolve, e),
      () => planAction(t.deps, resolve, e),
    ]) {
      expect((await call(t, fn)).result?.statusCode).toBe(401);
    }
    for (const fn of [getConversation, listConversations]) {
      await expect(fn(t.deps, resolve, e)).rejects.toMatchObject({ name: 'Unauthorized' });
    }
  });

  it('sends the resolved producer ID to the agent', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t, 'producer-a');
    expect(t.agent.requests[0]).toMatchObject({ kind: 'start', producerId: 'producer-a', conversationId: id });
  });
});

describe('request validation', () => {
  it('rejects bodies containing a producer ID or conversation ID with 400', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    for (const body of [
      { text: 'hi', producerId: 'producer-b' },
      { text: 'hi', producer_id: 'producer-b' },
      { text: 'hi', conversationId: CONV_B },
      { text: 'hi', extra: 1 },
    ]) {
      const r = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body })));
      expect(r.result?.statusCode).toBe(400);
    }
    const a = await call(t, () =>
      planAction(t.deps, resolve, makeEvent({ id, body: { action: 'set_consent', args: { producerId: 'x' } } })),
    );
    expect(a.result?.statusCode).toBe(400);
    const s = await call(t, () => planStart(t.deps, resolve, makeEvent({ body: { producerId: 'x' } })));
    expect(s.result?.statusCode).toBe(400);
  });

  it('rejects empty and over-long messages', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    for (const text of ['', 'x'.repeat(4001)]) {
      const r = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text } })));
      expect(r.result?.statusCode).toBe(400);
    }
    const ok = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'x'.repeat(4000) } })));
    expect(ok.result).toBeUndefined();
  });

  it('sends actions to the agent as { name, args }', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    await call(t, () =>
      planAction(t.deps, resolve, makeEvent({ id, body: { action: 'set_consent', args: { scope: 'internal' } } })),
    );
    expect(t.agent.requests.at(-1)).toMatchObject({
      kind: 'action',
      action: { name: 'set_consent', args: { scope: 'internal' } },
    });
  });
});

describe('ownership', () => {
  it("gives another producer's conversation the same 404 as a missing one", async () => {
    const t = makeDeps();
    const { id } = await startConversation(t, 'producer-a');
    const body = { text: 'hi' };
    const foreign = await call(t, () =>
      planMessage(t.deps, resolve, makeEvent({ producerId: 'producer-b', id, body })),
    );
    const missing = await call(t, () =>
      planMessage(t.deps, resolve, makeEvent({ producerId: 'producer-b', id: CONV_B, body })),
    );
    const malformed = await call(t, () =>
      planMessage(t.deps, resolve, makeEvent({ producerId: 'producer-b', id: 'nope', body })),
    );
    expect(foreign.result).toEqual({ statusCode: 404, body: { message: 'Not found' } });
    expect(missing.result).toEqual(foreign.result);
    expect(malformed.result).toEqual(foreign.result);
    const get = await getConversation(t.deps, resolve, makeEvent({ producerId: 'producer-b', id })).catch((e) =>
      toErrorResult(e, t.deps, 'get'),
    );
    expect(get).toEqual(foreign.result);
  });

  it('lists only the caller\'s conversations, newest first', async () => {
    const t = makeDeps();
    const first = await startConversation(t, 'producer-a');
    t.clock.t += 1000;
    await startConversation(t, 'producer-b');
    t.clock.t += 1000;
    const third = await startConversation(t, 'producer-a');
    const r = await listConversations(t.deps, resolve, makeEvent({ producerId: 'producer-a' }));
    const ids = (r.body as { conversations: Array<{ conversationId: string; status: string }> }).conversations.map(
      (c) => c.conversationId,
    );
    expect(ids).toEqual([third.id, first.id]);
  });

  it('creates conversation IDs on the server', async () => {
    const t = makeDeps();
    const { id, sink } = await startConversation(t);
    expect(sink.events[0]).toEqual({ type: 'conversation', conversationId: id });
    expect((await t.store.get(id))?.producerId).toBe('producer-a');
  });
});

describe('streaming turns', () => {
  it('passes agent events through in order, unchanged', async () => {
    const t = makeDeps();
    const events = [
      { type: 'text', seq: 1, text: 'Hello' },
      { type: 'claim', seq: 2, section: 'insights', claim: { id: 'c1' } },
      { type: 'step', seq: 3, step: 'playback', language: 'en' },
      { type: 'done', seq: 4 },
    ];
    t.agent.script.push(events);
    const { sink } = await startConversation(t);
    expect(sink.events.slice(1)).toEqual(events);
    expect(sink.ended).toBe(true);
  });

  it('writes claim events as they arrive, before the agent finishes', async () => {
    const t = makeDeps();
    const sink = new CaptureSink();
    const seenAtClaim: number[] = [];
    t.agent.script.push([{ type: 'claim', seq: 1 }, { type: 'done', seq: 2 }]);
    const plan = await planStart(t.deps, resolve, makeEvent({}));
    const origWrite = sink.write.bind(sink);
    sink.write = (c: string) => {
      origWrite(c);
      if (c.includes('"claim"')) seenAtClaim.push(sink.ended ? 1 : 0);
    };
    await plan.run(sink);
    expect(seenAtClaim).toEqual([0]);
  });

  it('ends with error then done when the agent fails mid-stream, and releases the lock', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.agent.script.push([{ type: 'text', seq: 1, text: 'partial' }, new Error('boom')]);
    const r = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'hi' } })));
    const types = r.sink.events.map((e) => e.type);
    expect(types).toEqual(['text', 'error', 'done']);
    expect(r.sink.events[1]).toMatchObject({ code: 'agent_failed' });
    expect((await t.store.get(id))?.lockExpiresAt).toBeUndefined();
  });

  it('does not repeat done when the agent fails after sending it', async () => {
    const t = makeDeps();
    t.agent.script.push([{ type: 'done', seq: 1 }, new Error('late')]);
    const { sink } = await startConversation(t);
    expect(sink.events.filter((e) => e.type === 'done')).toHaveLength(1);
  });

  it('marks the conversation closed when the stream carries step: closed', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.agent.script.push([{ type: 'step', seq: 1, step: 'closed' }, { type: 'done', seq: 2 }]);
    await call(t, () => planAction(t.deps, resolve, makeEvent({ id, body: { action: 'end' } })));
    const c = await t.store.get(id);
    expect(c?.status).toBe('closed');
    expect(c?.closedAt).toBeDefined();
  });

  it('returns 409 for messages and actions on a closed conversation', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    await t.store.markClosed(id, t.clock.t);
    const m = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'hi' } })));
    const a = await call(t, () => planAction(t.deps, resolve, makeEvent({ id, body: { action: 'end' } })));
    expect(m.result?.statusCode).toBe(409);
    expect(a.result?.statusCode).toBe(409);
    // Reading a closed conversation is still allowed.
    const g = await getConversation(t.deps, resolve, makeEvent({ id }));
    expect(g.statusCode).toBe(200);
    expect((g.body as { status: string }).status).toBe('closed');
  });
});

describe('turn lock', () => {
  it('returns 409 to a second request while a turn is in progress, then frees the lock', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    let second: { result?: JsonResult } | undefined;
    t.agent.onStream = async () => {
      t.agent.onStream = undefined;
      second = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'again' } })));
    };
    const first = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'hi' } })));
    expect(first.result).toBeUndefined();
    expect(second?.result?.statusCode).toBe(409);
    expect((await t.store.get(id))?.lockExpiresAt).toBeUndefined();
    const third = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'now' } })));
    expect(third.result).toBeUndefined();
  });

  it('frees an expired lock left by a crashed handler', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.store.items.get(id)!.lockExpiresAt = t.clock.t - 1;
    const r = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'hi' } })));
    expect(r.result).toBeUndefined();
  });
});

describe('activity time', () => {
  it('is set by start, messages and actions, and unchanged by GET routes', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.clock.t += 5000;
    await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'hi' } })));
    expect((await t.store.get(id))?.lastActivityAt).toBe(t.clock.t);
    const before = t.clock.t;
    t.clock.t += 5000;
    await getConversation(t.deps, resolve, makeEvent({ id }));
    await listConversations(t.deps, resolve, makeEvent({}));
    expect((await t.store.get(id))?.lastActivityAt).toBe(before);
  });
});

describe('logging', () => {
  it('never includes message or answer text', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.agent.script.push([{ type: 'text', seq: 1, text: 'ANSWER-SECRET' }, new Error('boom')]);
    await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'MESSAGE-SECRET' } })));
    const all = t.log.lines.join('\n');
    expect(all).not.toContain('MESSAGE-SECRET');
    expect(all).not.toContain('ANSWER-SECRET');
    expect(all).toContain(id);
  });
});

describe('inactivity sweep', () => {
  const IDLE = 30 * 60 * 1000;

  it('closes only idle open conversations', async () => {
    const t = makeDeps();
    const idle = await startConversation(t);
    t.clock.t += IDLE + 1;
    const active = await startConversation(t);
    t.agent.requests.length = 0;
    t.agent.script.push([{ type: 'step', seq: 1, step: 'closed' }, { type: 'done', seq: 2 }]);
    const r = await runSweep(t.deps, IDLE);
    expect(r.closedIdle).toBe(1);
    expect((await t.store.get(idle.id))?.status).toBe('closed');
    expect((await t.store.get(active.id))?.status).toBe('open');
    const closes = t.agent.requests.filter((q) => q.kind === 'auto_close');
    expect(closes).toHaveLength(1);
    expect(closes[0]).toMatchObject({ kind: 'auto_close', reason: 'inactivity' });
    // The sweep does not make anything look active, and releases its lock.
    expect((await t.store.get(idle.id))?.lockExpiresAt).toBeUndefined();
  });

  it('skips a conversation that became active before the sweep took the lock', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.clock.t += IDLE + 1;
    const store = t.store;
    const realAcquire = store.acquireLock.bind(store);
    store.acquireLock = async (...args) => {
      // A producer message lands between the scan and the lock.
      store.items.get(id)!.lastActivityAt = t.clock.t;
      return realAcquire(...args);
    };
    t.agent.requests.length = 0;
    const r = await runSweep(t.deps, IDLE);
    expect(r.closedIdle).toBe(0);
    expect(t.agent.requests).toHaveLength(0);
    expect((await store.get(id))?.status).toBe('open');
    expect((await store.get(id))?.lockExpiresAt).toBeUndefined();
  });

  it('skips a conversation whose turn lock is held', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.clock.t += IDLE + 1;
    t.store.items.get(id)!.lockExpiresAt = t.clock.t + 1000;
    t.agent.requests.length = 0;
    const r = await runSweep(t.deps, IDLE);
    expect(r.skipped).toBe(1);
    expect(t.agent.requests).toHaveLength(0);
  });

  it('marks a non-idle conversation closed when resume reports closed', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.agent.resumeResult = { step: 'closed' };
    const r = await runSweep(t.deps, IDLE);
    expect(r.closedByReconcile).toBe(1);
    expect((await t.store.get(id))?.status).toBe('closed');
  });

  it('leaves the conversation open when the agent does not report closed', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    t.clock.t += IDLE + 1;
    t.agent.script.push([{ type: 'done', seq: 1 }]);
    const r = await runSweep(t.deps, IDLE);
    expect(r.closedIdle).toBe(0);
    expect((await t.store.get(id))?.status).toBe('open');
  });
});

describe('review fixes', () => {
  it('rejects closed and busy turns during planning, before the agent is called', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    const before = t.agent.requests.length;

    t.store.items.get(id)!.lockExpiresAt = t.clock.t + 60_000;
    t.store.items.get(id)!.lockToken = 'someone-else';
    await expect(planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'hi' } }))).rejects.toMatchObject({
      name: 'Conflict',
      message: 'A turn is already in progress',
    });

    await t.store.markClosed(id, t.clock.t);
    await expect(planAction(t.deps, resolve, makeEvent({ id, body: { action: 'end' } }))).rejects.toMatchObject({
      name: 'Conflict',
      message: 'Conversation is closed',
    });
    expect(t.agent.requests.length).toBe(before);
  });

  it('reports "closed" when the conversation closes between load and lock', async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);
    const realAcquire = t.store.acquireLock.bind(t.store);
    t.store.acquireLock = async (...args) => {
      await t.store.markClosed(id, t.clock.t);
      return realAcquire(...args);
    };
    await expect(planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'hi' } }))).rejects.toMatchObject({
      message: 'Conversation is closed',
    });
  });

  it("does not let an expired turn release the lock of the turn that replaced it", async () => {
    const t = makeDeps();
    const { id } = await startConversation(t);

    // Turn 1 is held open until we let it finish.
    let finishFirst!: () => void;
    t.agent.onStream = () => new Promise<void>((r) => (finishFirst = r));
    const first = await planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'one' } }));
    const firstRun = first.run(new CaptureSink());
    await Promise.resolve();

    // Its lease expires, and turn 2 takes the lock.
    t.clock.t += t.deps.lockTtlMs + 1;
    t.agent.onStream = undefined;
    const second = await planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'two' } }));
    const secondToken = t.store.items.get(id)!.lockToken;

    // Turn 1 finishes. Turn 2's lock must survive.
    finishFirst();
    await firstRun;
    expect(t.store.items.get(id)!.lockToken).toBe(secondToken);
    const third = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'three' } })));
    expect(third.result?.statusCode).toBe(409);

    await second.run(new CaptureSink());
    expect(t.store.items.get(id)!.lockToken).toBeUndefined();
  });

  it('aborts an agent call that passes the turn time limit, then frees the lock', async () => {
    const t = makeDeps({ turnTimeoutMs: 20 });
    const { id } = await startConversation(t);
    t.agent.script.push([{ type: 'text', seq: 1, text: 'partial' }, HANG]);
    const r = await call(t, () => planMessage(t.deps, resolve, makeEvent({ id, body: { text: 'hi' } })));
    expect(r.sink.events.map((e) => e.type)).toEqual(['text', 'error', 'done']);
    expect(r.sink.ended).toBe(true);
    expect(t.agent.signals.at(-1)?.aborted).toBe(true);
    expect(t.store.items.get(id)!.lockExpiresAt).toBeUndefined();
    expect(t.log.lines.join('\n')).toContain('timeout');
  });

  it('keeps the turn limit inside the lock lease and the Lambda timeout', async () => {
    const { TURN_TIMEOUT_MS, DEFAULT_LOCK_TTL_MS, LAMBDA_TIMEOUT_MS } = await import('./types.js');
    expect(TURN_TIMEOUT_MS).toBeLessThan(LAMBDA_TIMEOUT_MS);
    expect(DEFAULT_LOCK_TTL_MS).toBeGreaterThan(LAMBDA_TIMEOUT_MS);
  });

  it('bounds the sweep\'s auto_close call too', async () => {
    const t = makeDeps({ turnTimeoutMs: 20 });
    const { id } = await startConversation(t);
    t.clock.t += 31 * 60 * 1000;
    t.agent.script.push([HANG]);
    const r = await runSweep(t.deps, 30 * 60 * 1000);
    expect(r.skipped).toBe(1);
    expect((await t.store.get(id))?.status).toBe('open');
    expect(t.store.items.get(id)!.lockExpiresAt).toBeUndefined();
  });
});

describe('review fixes, round 2', () => {
  it('skips a conversation whose resume stalls and still closes later idle ones', async () => {
    const t = makeDeps({ resumeTimeoutMs: 20 });
    const IDLE = 30 * 60 * 1000;
    const idle = await startConversation(t);
    t.clock.t += IDLE + 1;
    // Active (so the sweep reconciles it with resume), and its resume never answers.
    const stalled = await startConversation(t);
    t.agent.stallResume.add(stalled.id);
    // Scan order: the stalled conversation first, the idle one after it.
    const items = t.store.items;
    t.store.items = new Map([
      [stalled.id, items.get(stalled.id)!],
      [idle.id, items.get(idle.id)!],
    ]);
    t.agent.script.push([{ type: 'step', seq: 1, step: 'closed' }, { type: 'done', seq: 2 }]);

    const r = await runSweep(t.deps, IDLE);

    expect(r).toMatchObject({ closedIdle: 1, skipped: 1 });
    expect((await t.store.get(idle.id))?.status).toBe('closed');
    expect((await t.store.get(stalled.id))?.status).toBe('open');
    const resumeIdx = t.agent.requests.findIndex((q) => q.kind === 'resume');
    expect(t.agent.signals[resumeIdx]?.aborted).toBe(true);
  });

  it('returns 500 instead of hanging when GET resume stalls', async () => {
    const t = makeDeps({ resumeTimeoutMs: 20 });
    const { id } = await startConversation(t);
    t.agent.stallResume.add(id);
    const r = await getConversation(t.deps, resolve, makeEvent({ id })).catch((e) => toErrorResult(e, t.deps, 'get'));
    expect(r.statusCode).toBe(500);
  });
});
