import { randomUUID } from 'node:crypto';
import { Logger } from '@aws-lambda-powertools/logger';
import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { resolveIdentity, type IdentityFullResolver } from '../core/identity.js';
import { handleReview, type ReviewDeps } from '../core/review.js';
import { DynamoRecordStore } from '../core/reviewStore.js';

/**
 * Fair Trade USA review API (#27). Requires the `reviewer` role from the identity-resolution
 * function (#11). Normal (non-streaming) Lambda integration on the same REST API as the chat endpoint.
 */

const HEADERS = { 'content-type': 'application/json' };

function buildReviewDeps(): ReviewDeps {
  const table = process.env.RECORDS_TABLE;
  if (!table) throw new Error('Missing environment variable RECORDS_TABLE');
  // Logs carry the record ID, reviewer, route and status only. Never narrative text.
  const logger = new Logger({ serviceName: 'fex-review' });
  return {
    store: new DynamoRecordStore(table),
    log: {
      info: (m, f) => logger.info(m, f ?? {}),
      warn: (m, f) => logger.warn(m, f ?? {}),
      error: (m, f) => logger.error(m, f ?? {}),
    },
    now: () => Date.now(),
  };
}

/** Builds the handlers. Exported so tests can pass fakes; the Lambda exports below use the real ones. */
export function createReviewHandlers(getDeps: () => ReviewDeps, resolve: IdentityFullResolver = resolveIdentity) {
  const route =
    (name: string) =>
    async (event: APIGatewayProxyEvent): Promise<APIGatewayProxyResult> => {
      const result = await handleReview(getDeps(), resolve, name, event);
      return { statusCode: result.statusCode, headers: HEADERS, body: JSON.stringify(result.body) };
    };
  return {
    list: route('GET /records'),
    get: route('GET /records/{id}'),
    patch: route('PATCH /records/{id}'),
    approve: route('POST /records/{id}/approve'),
  };
}

let cached: ReviewDeps | undefined;
export const { list, get, patch, approve } = createReviewHandlers(() => (cached ??= buildReviewDeps()));
void randomUUID;
