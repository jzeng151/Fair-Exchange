import { Logger } from '@aws-lambda-powertools/logger';
import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { Unauthorized, resolveIdentity, type IdentityFullResolver } from '../core/identity.js';
import { handleMe, type MeDeps } from '../core/me.js';
import { DynamoRecordStore } from '../core/reviewStore.js';

/**
 * "Your record" API (#32). Requires the `producer` role from the identity-resolution function (#11).
 * Normal (non-streaming) Lambda integration on the same REST API as the chat endpoint.
 */

const HEADERS = {
  'content-type': 'application/json',
  ...(process.env.ALLOWED_ORIGIN ? { 'access-control-allow-origin': process.env.ALLOWED_ORIGIN, vary: 'Origin' } : {}),
};

export function createIdentityHandler(resolve: IdentityFullResolver = resolveIdentity) {
  return async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
    try {
      const identity = await resolve(event);
      return { statusCode: 200, headers: HEADERS, body: JSON.stringify({ user_id: identity.userId, roles: identity.roles }) };
    } catch (error) {
      return { statusCode: error instanceof Unauthorized ? 401 : 500, headers: HEADERS,
        body: JSON.stringify({ message: error instanceof Unauthorized ? 'Unauthorized' : 'Internal error' }) };
    }
  };
}
export const identity = createIdentityHandler();

function buildMeDeps(): MeDeps {
  const table = process.env.RECORDS_TABLE;
  if (!table) throw new Error('Missing environment variable RECORDS_TABLE');
  // Logs carry the producer ID, route and status only. Never narrative text.
  const logger = new Logger({ serviceName: 'fex-me' });
  return {
    store: new DynamoRecordStore(table),
    log: {
      info: (m, f) => logger.info(m, f ?? {}),
      warn: (m, f) => logger.warn(m, f ?? {}),
      error: (m, f) => logger.error(m, f ?? {}),
    },
  };
}

/** Builds the handlers. Exported so tests can pass fakes; the Lambda export below uses the real ones. */
export function createMeHandlers(getDeps: () => MeDeps, resolve: IdentityFullResolver = resolveIdentity) {
  const route =
    (name: string) =>
    async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
      const result = await handleMe(getDeps(), resolve, name, event);
      return { statusCode: result.statusCode, headers: HEADERS, body: JSON.stringify(result.body) };
    };
  return {
    records: route('GET /me/records'),
  };
}

let cached: MeDeps | undefined;
export const { records } = createMeHandlers(() => (cached ??= buildMeDeps()));
