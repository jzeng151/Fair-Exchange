// Issue #89: the API reads exactly what the agent runtime sends. The fixtures are produced on the agent side
// with the AgentCore Python SDK's own SSE encoder (agent/tests/test_wire_format.py), so both sides check the
// same bytes.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { AgentCoreClient, parseAgentStream } from './agent.js';

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url));
const SSE = fixture('agent-stream.sse');
const EVENTS = JSON.parse(fixture('agent-stream.events.json').toString('utf-8'));
const RESUME = JSON.parse(fixture('agent-resume.json').toString('utf-8'));

async function* chunks(bytes: Uint8Array, size: number) {
  for (let i = 0; i < bytes.length; i += size) yield bytes.slice(i, i + size);
}
const collect = async (it: AsyncIterable<unknown>) => {
  const out: unknown[] = [];
  for await (const x of it) out.push(x);
  return out;
};

describe('parseAgentStream', () => {
  it('reads the Server-Sent Events the AgentCore SDK sends for the agent generator', async () => {
    expect(await collect(parseAgentStream(chunks(SSE, SSE.length)))).toEqual(EVENTS);
  });

  it('reads the same events however the bytes are split, including inside a multi-byte character', async () => {
    for (const size of [1, 2, 3, 7, 64, 1000]) {
      expect(await collect(parseAgentStream(chunks(SSE, size)))).toEqual(EVENTS);
    }
  });

  it('still accepts newline-delimited JSON', async () => {
    const ndjson = new TextEncoder().encode(EVENTS.map((e: unknown) => JSON.stringify(e)).join('\n') + '\n');
    expect(await collect(parseAgentStream(chunks(ndjson, 5)))).toEqual(EVENTS);
  });

  it('ignores SSE comments and other SSE fields', async () => {
    const text = ': keep-alive\n\nevent: message\nid: 1\ndata: {"type":"done","seq":1}\n\n';
    expect(await collect(parseAgentStream(chunks(new TextEncoder().encode(text), 4)))).toEqual([{ type: 'done', seq: 1 }]);
  });
});

describe('AgentCoreClient', () => {
  const fakeSdk = (body: { stream?: Uint8Array; json?: unknown }) => {
    const sent: any[] = [];
    return {
      sent,
      send: async (command: any) => {
        sent.push(command.input);
        const response = body.stream
          ? chunks(body.stream, 50)
          : { transformToString: async () => JSON.stringify(body.json) };
        return { response };
      },
    };
  };
  const request = { kind: 'start' as const, producerId: 'P-1', conversationId: '11111111-2222-4333-8444-555555555555' };

  it('streams the agent events from an SSE response and asks for text/event-stream', async () => {
    const sdk = fakeSdk({ stream: SSE });
    const client = new AgentCoreClient('arn:runtime', sdk as any);
    expect(await collect(client.stream(request))).toEqual(EVENTS);
    expect(sdk.sent[0].accept).toBe('text/event-stream');
  });

  it('reads resume as the plain JSON object the agent returns, with step at the top', async () => {
    const sdk = fakeSdk({ json: RESUME });
    const client = new AgentCoreClient('arn:runtime', sdk as any);
    const resumed = await client.resume({ ...request, kind: 'resume' });
    expect(resumed.step).toBe(RESUME.step);
    expect(resumed).toEqual(RESUME);
  });
});
