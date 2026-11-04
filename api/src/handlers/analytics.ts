import { AthenaClient } from '@aws-sdk/client-athena';
import { Logger } from '@aws-lambda-powertools/logger';
import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import {
  ANALYTICS_TIMEOUT_MS,
  AnalyticsUnavailable,
  POLL_MS,
  loadNamedQueries,
  runAnalyticsQueries,
  type AthenaDeps,
  type QueryName,
} from '../analytics/athena.js';
import { buildResponse } from '../analytics/response.js';
import { requireRole, resolveIdentity, type IdentityFullResolver } from '../core/identity.js';
import { json, toErrorResult, type JsonResult } from '../core/routes.js';

/**
 * Analytics API (#29): `GET /analytics?include_pending=false`. Admin only.
 * Runs the fixed Athena named queries in parallel (20 s limit) and returns live counts with
 * small-cell suppression applied to both views together, plus seeded demo counts as a separate
 * series. See `api/README.md` for the response shape.
 */

export type AnalyticsDeps = AthenaDeps;

const ROUTE = 'GET /analytics';
const HEADERS = { 'content-type': 'application/json' };
const RETRY = json(503, { message: 'Analytics are temporarily unavailable. Please retry in a moment.' });

const asProxyResult = (r: JsonResult): APIGatewayProxyResult => ({
  statusCode: r.statusCode,
  headers: HEADERS,
  body: JSON.stringify(r.body),
});

/** Pending records are included only when include_pending is exactly "true". */
const includePending = (event: APIGatewayProxyEvent) => event.queryStringParameters?.include_pending === 'true';

/** Builds the handler. Exported so tests can pass fakes; the Lambda export below uses the real ones. */
export function createAnalyticsHandler(getDeps: () => AnalyticsDeps, resolve: IdentityFullResolver = resolveIdentity) {
  // The named queries' SQL is loaded once per container; a failed load is retried next request.
  let sql: Promise<Record<QueryName, string>> | undefined;

  return async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
    const d = getDeps();
    try {
      requireRole(await resolve(event), 'admin');
      const pending = includePending(event);
      const results = await runAnalyticsQueries(d, (signal) => {
        sql ??= loadNamedQueries(d, signal).catch((err) => {
          sql = undefined;
          throw err;
        });
        return sql;
      });
      return asProxyResult(json(200, buildResponse(results, pending)));
    } catch (err) {
      if (err instanceof AnalyticsUnavailable) return asProxyResult(RETRY);
      return asProxyResult(toErrorResult(err, d, ROUTE));
    }
  };
}

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`Missing environment variable ${name}`);
  return value;
};

let cached: AnalyticsDeps | undefined;
function buildDeps(): AnalyticsDeps {
  const logger = new Logger({ serviceName: 'fex-analytics' });
  return {
    athena: new AthenaClient({}),
    workGroup: required('ATHENA_WORKGROUP'),
    namedQueryIds: required('ANALYTICS_NAMED_QUERY_IDS').split(',').map((s) => s.trim()).filter(Boolean),
    timeoutMs: ANALYTICS_TIMEOUT_MS,
    pollMs: POLL_MS,
    log: {
      info: (m, f) => logger.info(m, f ?? {}),
      warn: (m, f) => logger.warn(m, f ?? {}),
      error: (m, f) => logger.error(m, f ?? {}),
    },
  };
}

export const handler = createAnalyticsHandler(() => (cached ??= buildDeps()));
