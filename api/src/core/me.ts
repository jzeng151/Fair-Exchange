import type { APIGatewayProxyEvent } from 'aws-lambda';
import { Forbidden, Unauthorized, requireRole, type IdentityFullResolver } from './identity.js';
import type { RecordStore, StoredRecord } from './reviewStore.js';
import type { Log } from './types.js';

/**
 * "Your record" API (#32 spec): GET /me/records. A producer sees only their own closed conversations
 * and exactly what FTUSA stored, in their own language. View-only; changes go through FTUSA.
 *
 * The producer ID comes only from the identity (#11); it is never read from the request. The fields
 * the spec says must never leave are stripped here: the English summary for a non-English producer,
 * every pii_* field, and the reviewer's identity. (The record schema has no decision log or ai_usage
 * field, so those cannot leak through this route.)
 */

export interface MeDeps {
  store: RecordStore;
  log: Log;
}

export interface MeResult {
  statusCode: number;
  body: unknown;
}

const json = (statusCode: number, body: unknown): MeResult => ({ statusCode, body });

const asString = (v: unknown): string | undefined => (typeof v === 'string' ? v : undefined);

// ---------------------------------------------------------------- record shaping

/** A closed record whose outcome is decided: completed with a stored consent, or declined. */
function isDecided(r: StoredRecord): boolean {
  if (typeof r.closed_at !== 'string') return false; // open conversations are resumed from the chat (#25)
  if (r.status === 'declined') return true;
  // Completed records carry a committed consent scope. A conversation that closed without a consent
  // choice, or whose consent a reopened playback cleared, has no decided outcome and is not listed (#32).
  const scope = (r.consent as { scope?: string } | undefined)?.scope;
  return r.status === 'completed' && (scope === 'internal' || scope === 'internal_and_outward');
}

/** The reviewer's value if set, otherwise the agent's, with a flag saying which. */
function effective<T>(reviewerValue: T | null | undefined, agentValue: T): { value: T; changed: boolean } {
  return reviewerValue == null ? { value: agentValue, changed: false } : { value: reviewerValue, changed: true };
}

/**
 * What a producer may see for one record. Completed records carry the effective (reviewer-or-agent)
 * summary and tags in the producer's language, with a changed_by_reviewer flag, plus the claims and
 * their citations, consent, feedback and review status. Declined records carry only the bare outcome.
 * Never included: summary_english for a non-English producer, pii_*, the decision log, ai_usage, the
 * reviewer identity.
 */
function present(r: StoredRecord): Record<string, unknown> {
  if (r.status === 'declined') {
    return { record_id: r.record_id, closed_at: r.closed_at, status: 'declined' };
  }

  const summary = effective(r.reviewer_summary_original as string | null | undefined, r.summary_original as string);
  const tags = effective(r.reviewer_tags as unknown, r.tags as unknown);
  const consent = r.consent as { scope: string; recorded_at: string };

  return {
    record_id: r.record_id,
    status: 'completed',
    closed_at: r.closed_at,
    language: r.language,
    consent: { scope: consent.scope, recorded_at: consent.recorded_at },
    summary: summary.value,
    changed_by_reviewer: summary.changed || tags.changed,
    tags: tags.value,
    insights: r.insights ?? [],
    peer_examples: r.peer_examples ?? [],
    earlier_answers: r.earlier_answers ?? [],
    feedback: r.feedback ?? null,
    review_status: r.review_status ?? 'pending',
    // summary_english, pii_flag, pii_review, reviewed_by/reviewed_at are deliberately omitted.
  };
}

// ---------------------------------------------------------------- routes

/** GET /me/records. The caller's decided, closed records, newest first. */
async function listMyRecords(deps: MeDeps, producerId: string): Promise<MeResult> {
  const records = (await deps.store.listClosedByProducer(producerId))
    .filter(isDecided)
    .sort((a, b) => String(b.closed_at).localeCompare(String(a.closed_at)));
  return json(200, { records: records.map(present) });
}

// ---------------------------------------------------------------- dispatch

function errorResult(err: unknown, deps: MeDeps, route: string): MeResult {
  if (err instanceof Unauthorized) return json(401, { message: 'Unauthorized' });
  if (err instanceof Forbidden) return json(403, { message: 'Forbidden' });
  deps.log.error('unhandled error', { route });
  return json(500, { message: 'Internal error' });
}

/**
 * Handles one "your record" request. `route` is the API Gateway resource ("GET /me/records").
 * Logs the producer ID, route and status only, never narrative text.
 */
export async function handleMe(
  deps: MeDeps,
  resolve: IdentityFullResolver,
  route: string,
  event: APIGatewayProxyEvent,
): Promise<MeResult> {
  let producerId: string | undefined;
  let result: MeResult;
  try {
    const identity = requireRole(await resolve(event), 'producer');
    // A producer identity always carries its producer ID (#11); guard anyway.
    if (!identity.producerId) throw new Forbidden();
    producerId = identity.producerId;
    switch (route) {
      case 'GET /me/records':
        result = await listMyRecords(deps, producerId);
        break;
      default:
        result = json(404, { message: 'Not found' });
    }
  } catch (err) {
    result = errorResult(err, deps, route);
  }
  deps.log.info('me request', { route, producerId: asString(producerId), status: result.statusCode });
  return result;
}
