import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import {
  resolveCaller,
  resolveIdentity,
  type IdentityFullResolver,
  type IdentityResolver,
} from '../core/identity.js';
import {
  getConversation,
  getMe,
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

const HEADERS = { 'content-type': 'application/json' };

const asProxyResult = (r: JsonResult): APIGatewayProxyResult => ({
  statusCode: r.statusCode,
  headers: HEADERS,
  body: JSON.stringify(r.body),
});

type Planner = (d: Deps, r: IdentityResolver, e: APIGatewayProxyEvent) => Promise<StreamPlan>;

/**
 * Builds the handlers. Exported so tests can pass fakes; the Lambda exports below use the real ones.
 * `resolve` yields the producer ID for the chat routes; `resolveFull` yields the whole identity for
 * GET /me. Both come from the one identity-resolution function (#11), so a single fake drives both.
 */
export function createHandlers(
  getDeps: () => Deps,
  resolve: IdentityResolver = resolveCaller,
  resolveFull: IdentityFullResolver = resolveIdentity,
) {
  /**
   * Plans first. Every 4xx (including 409 for a closed conversation or a busy lock) comes
   * from planning, so it is sent as that status before a 200 stream is ever opened.
   */
  const streaming = (route: string, plan: Planner) =>
    awslambda.streamifyResponse(async (event: APIGatewayProxyEvent, responseStream) => {
      const d = getDeps();
      let prepared: StreamPlan;
      try {
        prepared = await plan(d, resolve, event);
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
      let out: ReturnType<typeof awslambda.HttpResponseStream.from>;
      try {
        out = awslambda.HttpResponseStream.from(responseStream, {
          statusCode: 200,
          headers: { 'content-type': 'application/x-ndjson' },
        });
      } catch (err) {
        await prepared.abandon();
        throw err;
      }
      d.log.info('turn started', { route, conversationId: prepared.conversationId });
      const started = d.now();
      await prepared.run({ write: (c) => void out.write(c), end: () => out.end() });
      d.log.info('turn finished', { route, conversationId: prepared.conversationId, ms: d.now() - started });
    });

  const plain =
    <R>(route: string, r: R, op: (d: Deps, r: R, e: APIGatewayProxyEvent) => Promise<JsonResult>) =>
    async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
      const d = getDeps();
      try {
        return asProxyResult(await op(d, r, event));
      } catch (err) {
        return asProxyResult(toErrorResult(err, d, route));
      }
    };

  return {
    start: streaming('POST /conversations', planStart),
    message: streaming('POST /conversations/{id}/messages', planMessage),
    action: streaming('POST /conversations/{id}/actions', planAction),
    get: plain('GET /conversations/{id}', resolve, getConversation),
    list: plain('GET /conversations', resolve, listConversations),
    me: plain('GET /me', resolveFull, getMe),
  };
}

let cached: Deps | undefined;
const handlers = createHandlers(() => (cached ??= buildDeps()));

export const { start, message, action, get, list, me } = handlers;
