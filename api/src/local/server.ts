/**
 * The REAL chat API route logic (#25) served locally over HTTP (#101), for running the whole chain on one
 * machine. Same planners, validation, ownership checks, turn lock and streaming as the Lambda handlers in
 * `handlers/conversations.ts`; only the transport differs (node:http instead of Lambda response streaming),
 * and conversations are kept in memory.
 *
 * LOCAL ONLY: the caller is identified by the `x-demo-producer-id` header, a stand-in for the sign-in that
 * API Gateway's authorizer provides on AWS (#11). Never deploy this.
 */
import { randomUUID } from 'node:crypto';
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { resolveCaller } from '../core/identity.js';
import {
  getConversation, listConversations, planAction, planMessage, planStart, toErrorResult, type JsonResult,
  type StreamPlan,
} from '../core/routes.js';
import { MemoryStore } from '../core/testing.js';
import {
  DEFAULT_LOCK_TTL_MS, RESUME_TIMEOUT_MS, TURN_TIMEOUT_MS, type AgentClient, type Deps, type Log,
} from '../core/types.js';

export const IDENTITY_HEADER = 'x-demo-producer-id';

const consoleLog: Log = {
  info: (m, f) => console.log(JSON.stringify({ level: 'info', m, ...f })),
  warn: (m, f) => console.warn(JSON.stringify({ level: 'warn', m, ...f })),
  error: (m, f) => console.error(JSON.stringify({ level: 'error', m, ...f })),
};

export function localDeps(agent: AgentClient, log: Log = consoleLog): Deps {
  return {
    store: new MemoryStore(), agent, log, now: () => Date.now(), newId: () => randomUUID(),
    turnTimeoutMs: TURN_TIMEOUT_MS, resumeTimeoutMs: RESUME_TIMEOUT_MS, lockTtlMs: DEFAULT_LOCK_TTL_MS,
  };
}

const readBody = (req: IncomingMessage) => new Promise<string>((resolve, reject) => {
  let body = '';
  req.on('data', (c) => (body += c));
  req.on('end', () => resolve(body));
  req.on('error', reject);
});

function toEvent(req: IncomingMessage, body: string, id?: string): APIGatewayProxyEvent {
  const producerId = req.headers[IDENTITY_HEADER];
  return {
    body: body || null,
    pathParameters: id ? { id } : null,
    requestContext: { authorizer: typeof producerId === 'string' ? { producerId } : undefined },
  } as unknown as APIGatewayProxyEvent;
}

// x-demo-passcode is what the deployed stand-in also checks (core/demoAuth.ts); locally it is accepted and ignored.
const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': `content-type, ${IDENTITY_HEADER}, x-demo-passcode`,
};

function sendJson(res: ServerResponse, r: JsonResult): void {
  res.writeHead(r.statusCode, { 'content-type': 'application/json', ...CORS });
  res.end(JSON.stringify(r.body));
}

type Planner = typeof planStart;
type Reader = typeof getConversation;

export function createLocalServer(opts: { agent: AgentClient; log?: Log }): Server {
  const deps = localDeps(opts.agent, opts.log);

  async function streaming(res: ServerResponse, route: string, plan: Planner, event: APIGatewayProxyEvent) {
    let prepared: StreamPlan;
    try {
      prepared = await plan(deps, resolveCaller, event);
    } catch (err) {
      return sendJson(res, toErrorResult(err, deps, route)); // every 4xx comes from planning, as on AWS
    }
    res.writeHead(200, { 'content-type': 'application/x-ndjson', ...CORS });
    await prepared.run({ write: (c) => void res.write(c), end: () => res.end() });
  }

  async function plain(res: ServerResponse, route: string, op: Reader, event: APIGatewayProxyEvent) {
    try {
      sendJson(res, await op(deps, resolveCaller, event));
    } catch (err) {
      sendJson(res, toErrorResult(err, deps, route));
    }
  }

  return createServer(async (req, res) => {
    const path = (req.url ?? '/').split('?')[0]!;
    if (req.method === 'OPTIONS') { res.writeHead(204, CORS); return res.end(); }
    const body = await readBody(req);
    const m = path.match(/^\/conversations\/([^/]+)(\/messages|\/actions)?$/);
    if (req.method === 'POST' && path === '/conversations') {
      return streaming(res, 'POST /conversations', planStart, toEvent(req, body));
    }
    if (req.method === 'GET' && path === '/conversations') {
      return plain(res, 'GET /conversations', listConversations, toEvent(req, body));
    }
    if (m && req.method === 'POST' && m[2] === '/messages') {
      return streaming(res, 'POST /conversations/{id}/messages', planMessage, toEvent(req, body, m[1]));
    }
    if (m && req.method === 'POST' && m[2] === '/actions') {
      return streaming(res, 'POST /conversations/{id}/actions', planAction, toEvent(req, body, m[1]));
    }
    if (m && req.method === 'GET' && !m[2]) {
      return plain(res, 'GET /conversations/{id}', getConversation, toEvent(req, body, m[1]));
    }
    sendJson(res, { statusCode: 404, body: { message: 'Not found' } });
  });
}
