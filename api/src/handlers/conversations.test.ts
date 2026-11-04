import type { APIGatewayProxyEvent, Context } from 'aws-lambda';
import { beforeAll, describe, expect, it } from 'vitest';
import { makeDeps, makeEvent } from '../core/testing.js';

/**
 * Drives the real Lambda handlers through a stand-in for the `awslambda` streaming
 * globals, so status codes are checked where the client actually sees them.
 */
interface Captured {
  statusCode?: number;
  contentType?: string;
  body: string;
  ended: boolean;
}

class FakeResponseStream {
  captured: Captured = { body: '', ended: false };
  write(chunk: string) {
    this.captured.body += chunk;
    return true;
  }
  end() {
    this.captured.ended = true;
  }
}

type StreamHandler = (event: APIGatewayProxyEvent, stream: FakeResponseStream, ctx: Context) => Promise<void>;

let createHandlers: typeof import('./conversations.js').createHandlers;

beforeAll(async () => {
  (globalThis as unknown as { awslambda: unknown }).awslambda = {
    streamifyResponse: (fn: StreamHandler) => fn,
    HttpResponseStream: {
      from: (stream: FakeResponseStream, meta: { statusCode: number; headers: Record<string, string> }) => {
        stream.captured.statusCode = meta.statusCode;
        stream.captured.contentType = meta.headers['content-type'];
        return stream;
      },
    },
  };
  // The module builds its default handlers at import; they read env only when invoked.
  ({ createHandlers } = await import('./conversations.js'));
});

async function invoke(handler: unknown, event: APIGatewayProxyEvent): Promise<Captured> {
  const stream = new FakeResponseStream();
  await (handler as StreamHandler)(event, stream, {} as Context);
  return stream.captured;
}

function setup() {
  const t = makeDeps();
  return { t, h: createHandlers(() => t.deps) };
}

async function start(h: ReturnType<typeof setup>['h']) {
  const r = await invoke(h.start, makeEvent({}));
  const first = JSON.parse(r.body.split('\n')[0]!) as { conversationId: string };
  return { r, id: first.conversationId };
}

describe('streaming handlers', () => {
  it('streams a turn as 200 ndjson', async () => {
    const { h } = setup();
    const { r } = await start(h);
    expect(r.statusCode).toBe(200);
    expect(r.contentType).toBe('application/x-ndjson');
    expect(r.ended).toBe(true);
  });

  it('returns HTTP 409 for a message on a closed conversation', async () => {
    const { t, h } = setup();
    const { id } = await start(h);
    await t.store.markClosed(id, t.clock.t);
    const r = await invoke(h.message, makeEvent({ id, body: { text: 'hi' } }));
    expect(r.statusCode).toBe(409);
    expect(r.contentType).toBe('application/json');
    expect(JSON.parse(r.body)).toEqual({ message: 'Conversation is closed' });
  });

  it('returns HTTP 409 for an action while another turn holds the lock', async () => {
    const { t, h } = setup();
    const { id } = await start(h);
    t.store.items.get(id)!.lockExpiresAt = t.clock.t + 60_000;
    t.store.items.get(id)!.lockToken = 'other-turn';
    const r = await invoke(h.action, makeEvent({ id, body: { action: 'end' } }));
    expect(r.statusCode).toBe(409);
    expect(JSON.parse(r.body)).toEqual({ message: 'A turn is already in progress' });
    // The other turn's lock is untouched.
    expect(t.store.items.get(id)!.lockToken).toBe('other-turn');
  });

  it('returns 400, 401 and 404 as plain statuses', async () => {
    const { h } = setup();
    const { id } = await start(h);
    expect((await invoke(h.message, makeEvent({ id, body: { text: 'hi', producerId: 'x' } }))).statusCode).toBe(400);
    expect((await invoke(h.message, makeEvent({ producerId: null, id, body: { text: 'hi' } }))).statusCode).toBe(401);
    expect(
      (await invoke(h.message, makeEvent({ producerId: 'producer-b', id, body: { text: 'hi' } }))).statusCode,
    ).toBe(404);
  });

  it('serves the GET routes as normal proxy responses', async () => {
    const { h } = setup();
    const { id } = await start(h);
    const got = await h.get(makeEvent({ id }));
    expect(got.statusCode).toBe(200);
    const foreign = await h.get(makeEvent({ producerId: 'producer-b', id }));
    expect(foreign.statusCode).toBe(404);
    const listed = await h.list(makeEvent({}));
    expect(JSON.parse(listed.body).conversations).toHaveLength(1);
  });
});
