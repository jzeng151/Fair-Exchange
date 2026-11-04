import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { resolveCaller } from '../core/identity.js';
import {
  getConversation,
  listConversations,
  planAction,
  planMessage,
  planStart,
  toErrorResult,
  type JsonResult,
  type StreamPlan,
} from '../core/routes.js';
import { buildDeps } from '../core/runtime.js';
import type { Deps } from '../core/types.js';

/**
 * Chat API (#25). Streaming routes use Lambda response streaming and emit
 * application/x-ndjson. The producer ID is resolved from the caller's identity
 * (resolveCaller, #11), never taken from the request.
 */
let cached: Deps | undefined;
const deps = (): Deps => (cached ??= buildDeps());

const HEADERS = { 'content-type': 'application/json' };

const asProxyResult = (r: JsonResult): APIGatewayProxyResult => ({
  statusCode: r.statusCode,
  headers: HEADERS,
  body: JSON.stringify(r.body),
});

/** Wraps a streaming route. Plain status codes are sent before the stream starts. */
const streaming = (route: string, plan: (d: Deps, e: APIGatewayProxyEvent) => Promise<StreamPlan>) =>
  awslambda.streamifyResponse(async (event: APIGatewayProxyEvent, responseStream) => {
    const d = deps();
    let prepared: StreamPlan;
    try {
      prepared = await plan(d, event);
    } catch (err) {
      const r = toErrorResult(err, d, route);
      const out = awslambda.HttpResponseStream.from(responseStream, {
        statusCode: r.statusCode,
        headers: HEADERS,
      });
      out.write(JSON.stringify(r.body));
      out.end();
      return;
    }
    const out = awslambda.HttpResponseStream.from(responseStream, {
      statusCode: 200,
      headers: { 'content-type': 'application/x-ndjson' },
    });
    d.log.info('turn started', { route, conversationId: prepared.conversationId });
    const started = d.now();
    await prepared.run({ write: (c) => void out.write(c), end: () => out.end() });
    d.log.info('turn finished', { route, conversationId: prepared.conversationId, ms: d.now() - started });
  });

const plain =
  (route: string, op: (d: Deps, e: APIGatewayProxyEvent) => Promise<JsonResult>) =>
  async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
    const d = deps();
    try {
      return asProxyResult(await op(d, event));
    } catch (err) {
      return asProxyResult(toErrorResult(err, d, route));
    }
  };

export const start = streaming('POST /conversations', (d, e) => planStart(d, resolveCaller, e));
export const message = streaming('POST /conversations/{id}/messages', (d, e) =>
  planMessage(d, resolveCaller, e),
);
export const action = streaming('POST /conversations/{id}/actions', (d, e) =>
  planAction(d, resolveCaller, e),
);
export const get = plain('GET /conversations/{id}', (d, e) => getConversation(d, resolveCaller, e));
export const list = plain('GET /conversations', (d, e) => listConversations(d, resolveCaller, e));
