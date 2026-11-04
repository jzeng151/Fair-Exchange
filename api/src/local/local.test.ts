// Issue #101: the real chat API route logic served locally over HTTP, calling an agent over HTTP.
import { readFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, describe, expect, it } from 'vitest';
import { ScriptedAgent } from '../core/testing.js';
import { HttpAgentClient } from './agentClient.js';
import { createLocalServer } from './server.js';

const fixture = (name: string) => readFileSync(new URL(`../core/fixtures/${name}`, import.meta.url));
const SSE = fixture('agent-stream.sse');
const EVENTS = JSON.parse(fixture('agent-stream.events.json').toString('utf-8'));
const RESUME = JSON.parse(fixture('agent-resume.json').toString('utf-8'));

const servers: Server[] = [];
afterEach(async () => {
  await Promise.all(servers.splice(0).map((s) => new Promise((r) => s.close(r))));
});
async function listen(server: Server): Promise<string> {
  servers.push(server);
  await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}
const collect = async <T>(it: AsyncIterable<T>) => {
  const out: T[] = [];
  for await (const x of it) out.push(x);
  return out;
};
const request = { kind: 'start' as const, producerId: 'P-1', conversationId: '11111111-2222-4333-8444-555555555555' };

describe('HttpAgentClient (calls an agent served like AgentCore)', () => {
  it('streams events from the SSE the agent sends, posting the request as JSON to /invocations', async () => {
    const seen: { url?: string; body?: string; accept?: string } = {};
    const url = await listen(createServer((req, res) => {
      let body = '';
      req.on('data', (c) => (body += c));
      req.on('end', () => {
        Object.assign(seen, { url: req.url, body, accept: req.headers.accept });
        res.writeHead(200, { 'content-type': 'text/event-stream' });
        for (let i = 0; i < SSE.length; i += 97) res.write(SSE.subarray(i, i + 97)); // arrives in pieces
        res.end();
      });
    }));
    expect(await collect(new HttpAgentClient(url).stream(request))).toEqual(EVENTS);
    expect(seen.url).toBe('/invocations');
    expect(JSON.parse(seen.body!)).toEqual(request);
    expect(seen.accept).toBe('text/event-stream');
  });

  it('reads resume as plain JSON', async () => {
    const url = await listen(createServer((_req, res) => {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify(RESUME));
    }));
    expect(await new HttpAgentClient(url).resume({ ...request, kind: 'resume' })).toEqual(RESUME);
  });

  it('fails clearly when the agent answers with an HTTP error', async () => {
    const url = await listen(createServer((_req, res) => { res.writeHead(500); res.end('boom'); }));
    await expect(collect(new HttpAgentClient(url).stream(request))).rejects.toThrow(/500/);
  });
});

describe('local chat API server', () => {
  const start = async (agent = new ScriptedAgent()) => ({ url: await listen(createLocalServer({ agent })), agent });
  const post = (url: string, path: string, body: unknown, producer = 'P-1') =>
    fetch(`${url}${path}`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-demo-producer-id': producer },
      body: JSON.stringify(body) });

  it('starts a conversation and streams the agent events as NDJSON, through the real route logic', async () => {
    const agent = new ScriptedAgent();
    agent.script.push([{ type: 'text', seq: 1, text: 'Hola' }, { type: 'step', seq: 2, step: 'intake' }, { type: 'done', seq: 3 }]);
    const { url } = await start(agent);
    const res = await post(url, '/conversations', {});
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toContain('application/x-ndjson');
    const lines = (await res.text()).trim().split('\n').map((l) => JSON.parse(l));
    expect(lines.map((e) => e.type)).toEqual(['conversation', 'text', 'step', 'done'].filter((t) => lines.some((e) => e.type === t)));
    expect(agent.requests[0]).toMatchObject({ kind: 'start', producerId: 'P-1' });
  });

  it('takes the producer only from the local identity header, never the body', async () => {
    const { url } = await start();
    const res = await post(url, '/conversations', { producerId: 'someone-else' });
    expect(res.status).toBe(400); // the real validator rejects IDs in the body
  });

  it('returns 401 without an identity, and 404 for an unknown route', async () => {
    const { url } = await start();
    expect((await fetch(`${url}/conversations`, { method: 'POST', body: '{}' })).status).toBe(401);
    expect((await fetch(`${url}/nope`)).status).toBe(404);
  });

  it("another producer's conversation is a 404, as on AWS", async () => {
    const agent = new ScriptedAgent();
    agent.script.push([{ type: 'done', seq: 1 }]);
    const { url } = await start(agent);
    const lines = (await (await post(url, '/conversations', {})).text()).trim().split('\n').map((l) => JSON.parse(l));
    const id = lines.find((e) => e.conversationId)?.conversationId ?? lines[0].conversationId;
    const res = await fetch(`${url}/conversations/${id}`, { headers: { 'x-demo-producer-id': 'P-2' } });
    expect(res.status).toBe(404);
  });
});
