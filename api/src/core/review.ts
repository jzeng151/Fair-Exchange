import type { APIGatewayProxyEvent } from 'aws-lambda';
import { Ajv, type ValidateFunction } from 'ajv';
import addFormatsModule from 'ajv-formats';
import recordSchema from '../types/conversation-record.schema.json' with { type: 'json' };
import { Forbidden, Unauthorized, requireRole, type IdentityFullResolver } from './identity.js';
import { VersionConflict, type RecordStore, type StoredRecord } from './reviewStore.js';
import type { Log } from './types.js';

/**
 * Review API (#27 spec): list closed completed records, correct tags, summaries and the PII decision, approve.
 * The agent's fields never change; every write is validated against the generated record schema first.
 */

export interface ReviewDeps {
  store: RecordStore;
  log: Log;
  now: () => number;
}

export interface ReviewResult {
  statusCode: number;
  body: unknown;
}

const json = (statusCode: number, body: unknown): ReviewResult => ({ statusCode, body });

class BadRequest extends Error {}
class NotFound extends Error {}
class Conflict extends Error {
  constructor(
    readonly reason: string,
    readonly currentVersion?: number,
  ) {
    super(reason);
  }
}

// ---------------------------------------------------------------- schema validation

type AddFormats = (ajv: Ajv) => Ajv;
const addFormats = ((addFormatsModule as unknown as { default?: AddFormats }).default ??
  (addFormatsModule as unknown as AddFormats)) as AddFormats;

let validator: ValidateFunction | undefined;
/** Validates a whole record. `strict: false` because Pydantic adds keywords (e.g. `discriminator`) that Ajv does not know. */
export function validateRecord(record: unknown): string | undefined {
  if (!validator) {
    const ajv = new Ajv({ strict: false, allErrors: false });
    addFormats(ajv);
    validator = ajv.compile(recordSchema);
  }
  if (validator(record)) return undefined;
  const first = validator.errors?.[0];
  return first ? `${first.instancePath || '/'} ${first.message ?? 'is invalid'}` : 'Record is invalid';
}

// ---------------------------------------------------------------- request parsing

const REVIEW_STATUSES = ['pending', 'reviewed'];
const EVIDENCE = ['full', 'limited'];
const PII_FILTERS = ['unresolved', 'any'];
const PATCH_FIELDS = ['reviewer_tags', 'reviewer_summary_original', 'reviewer_summary_english', 'pii_review'];
/** A record ID is a conversation ID: a v4 UUID. Anything else cannot exist. */
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

function parseBody(body: string | null | undefined, allowed: string[]): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body ?? '');
  } catch {
    throw new BadRequest('Body must be a JSON object');
  }
  if (!isObject(parsed)) throw new BadRequest('Body must be a JSON object');
  for (const key of Object.keys(parsed)) {
    if (/^(producer|conversation|record)_?id$/i.test(key)) {
      throw new BadRequest('IDs cannot be set in the body');
    }
    if (!allowed.includes(key)) throw new BadRequest(`Unknown field: ${key}`);
  }
  if (!Number.isInteger(parsed.version) || (parsed.version as number) < 1) {
    throw new BadRequest('version must be a positive integer');
  }
  return parsed;
}

function pathRecordId(event: APIGatewayProxyEvent): string {
  const id = event.pathParameters?.id;
  if (typeof id !== 'string' || !UUID_V4.test(id)) throw new NotFound();
  return id;
}

function oneOf(value: string | undefined, allowed: string[], name: string): string | undefined {
  if (value === undefined) return undefined;
  if (!allowed.includes(value)) throw new BadRequest(`${name} must be one of: ${allowed.join(', ')}`);
  return value;
}

// ---------------------------------------------------------------- helpers

type Reviewable = StoredRecord & { status: 'completed'; closed_at: string };

/** Open and declined records are not reviewable. They look the same as missing ones. */
function isReviewable(record: StoredRecord | undefined): record is Reviewable {
  return !!record && record.status === 'completed' && typeof record.closed_at === 'string';
}

async function loadReviewable(deps: ReviewDeps, event: APIGatewayProxyEvent): Promise<Reviewable> {
  const record = await deps.store.get(pathRecordId(event));
  if (!isReviewable(record)) throw new NotFound();
  return record;
}

const asString = (v: unknown): string | undefined => (typeof v === 'string' ? v : undefined);

/** The reviewer's value if set, otherwise the agent's. */
const effectiveTags = (r: StoredRecord): unknown => r.reviewer_tags ?? r.tags;

const summarize = (r: StoredRecord) => ({
  record_id: r.record_id,
  closed_at: r.closed_at,
  language: r.language,
  entity_type: r.entity_type,
  tags: effectiveTags(r),
  review_status: r.review_status,
  pii_flag: r.pii_flag,
  pii_review: r.pii_review ?? null,
  evidence: r.evidence,
  version: r.version,
});

async function write(deps: ReviewDeps, updated: StoredRecord, expectedVersion: number): Promise<void> {
  const problem = validateRecord(updated);
  if (problem) throw new BadRequest(`Record would be invalid: ${problem}`);
  try {
    await deps.store.replace(updated, expectedVersion);
  } catch (err) {
    if (err instanceof VersionConflict) throw new Conflict('version_conflict', err.currentVersion);
    throw err;
  }
}

/** Common bookkeeping for every write: bump the version and the update time. */
function bumped(record: StoredRecord, deps: ReviewDeps, changes: Record<string, unknown>): StoredRecord {
  return {
    ...record,
    ...changes,
    updated_at: new Date(deps.now()).toISOString(),
    version: (record.version as number) + 1,
  } as StoredRecord;
}

// ---------------------------------------------------------------- routes

/** GET /records */
async function listRecords(deps: ReviewDeps, event: APIGatewayProxyEvent): Promise<ReviewResult> {
  const q = event.queryStringParameters ?? {};
  const reviewStatus = oneOf(q.review_status, REVIEW_STATUSES, 'review_status');
  const pii = oneOf(q.pii, PII_FILTERS, 'pii');
  const evidence = oneOf(q.evidence, EVIDENCE, 'evidence');

  const records = (await deps.store.listClosedCompleted())
    .filter(isReviewable)
    .filter((r) => !reviewStatus || r.review_status === reviewStatus)
    .filter((r) => !evidence || r.evidence === evidence)
    .filter((r) => {
      if (!pii) return true;
      if (pii === 'any') return r.pii_flag === true;
      return r.pii_flag === true && !r.pii_review; // unresolved: flagged with no review decision
    })
    .sort((a, b) => b.closed_at.localeCompare(a.closed_at));
  return json(200, { records: records.map(summarize) });
}

/** GET /records/{id} */
async function getRecord(deps: ReviewDeps, event: APIGatewayProxyEvent): Promise<ReviewResult> {
  return json(200, await loadReviewable(deps, event));
}

/** PATCH /records/{id} */
async function patchRecord(deps: ReviewDeps, event: APIGatewayProxyEvent): Promise<ReviewResult> {
  const body = parseBody(event.body, ['version', ...PATCH_FIELDS]);
  const changes = Object.fromEntries(PATCH_FIELDS.filter((f) => f in body).map((f) => [f, body[f]]));
  if (Object.keys(changes).length === 0) throw new BadRequest(`Send at least one of: ${PATCH_FIELDS.join(', ')}`);

  const record = await loadReviewable(deps, event);
  if (record.review_status === 'reviewed') throw new Conflict('approved', record.version as number);
  if (record.version !== body.version) throw new Conflict('version_conflict', record.version as number);

  await write(deps, bumped(record, deps, changes), body.version as number);
  return json(200, await loadReviewable(deps, event));
}

/** POST /records/{id}/approve */
async function approveRecord(
  deps: ReviewDeps,
  event: APIGatewayProxyEvent,
  reviewerId: string,
): Promise<ReviewResult> {
  const body = parseBody(event.body, ['version']);
  const record = await loadReviewable(deps, event);
  if (record.review_status === 'reviewed') throw new Conflict('approved', record.version as number);
  if (record.version !== body.version) throw new Conflict('version_conflict', record.version as number);
  if (record.pii_flag === true && !record.pii_review) throw new Conflict('pii_unresolved', record.version as number);

  const now = new Date(deps.now()).toISOString();
  await write(
    deps,
    bumped(record, deps, { review_status: 'reviewed', reviewed_by: reviewerId, reviewed_at: now }),
    body.version as number,
  );
  return json(200, await loadReviewable(deps, event));
}

// ---------------------------------------------------------------- dispatch

function errorResult(err: unknown, deps: ReviewDeps, route: string, reviewer?: string): ReviewResult {
  if (err instanceof Unauthorized) return json(401, { message: 'Unauthorized' });
  if (err instanceof Forbidden) return json(403, { message: 'Forbidden' });
  if (err instanceof BadRequest) return json(400, { message: err.message });
  if (err instanceof NotFound) return json(404, { message: 'Not found' });
  if (err instanceof Conflict) {
    return json(409, { message: 'Conflict', reason: err.reason, currentVersion: err.currentVersion });
  }
  deps.log.error('unhandled error', { route, reviewer });
  return json(500, { message: 'Internal error' });
}

/**
 * Handles one review request. `route` is the API Gateway resource ("GET /records", ...).
 * Logs the record ID, reviewer, route and status only, never narrative text.
 */
export async function handleReview(
  deps: ReviewDeps,
  resolve: IdentityFullResolver,
  route: string,
  event: APIGatewayProxyEvent,
): Promise<ReviewResult> {
  let reviewer: string | undefined;
  let result: ReviewResult;
  try {
    const identity = requireRole(await resolve(event), 'reviewer');
    reviewer = identity.userId;
    switch (route) {
      case 'GET /records':
        result = await listRecords(deps, event);
        break;
      case 'GET /records/{id}':
        result = await getRecord(deps, event);
        break;
      case 'PATCH /records/{id}':
        result = await patchRecord(deps, event);
        break;
      case 'POST /records/{id}/approve':
        result = await approveRecord(deps, event, reviewer);
        break;
      default:
        throw new NotFound();
    }
  } catch (err) {
    result = errorResult(err, deps, route, reviewer);
  }
  deps.log.info('review request', {
    route,
    reviewer,
    recordId: asString(event.pathParameters?.id),
    status: result.statusCode,
  });
  return result;
}
