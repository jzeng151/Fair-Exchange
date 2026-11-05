import type { APIGatewayProxyEvent } from 'aws-lambda';
import { describe, expect, it } from 'vitest';
import { Unauthorized, type Identity, type IdentityFullResolver } from '../core/identity.js';
import { validateRecord } from '../core/review.js';
import { VersionConflict, type RecordStore, type StoredRecord } from '../core/reviewStore.js';
import { CaptureLog } from '../core/testing.js';
import { createReviewHandlers } from './review.js';

/** Seam 2: the real handlers, a fake identity resolver and an in-memory record store. */

const ID = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const NOW = Date.parse('2026-11-05T09:00:00Z');

function record(n: number, overrides: Record<string, unknown> = {}): StoredRecord {
  return {
    record_id: ID(n),
    producer_id: 'producer-a',
    created_at: '2026-11-04T10:00:00Z',
    source: 'agent conversation',
    updated_at: '2026-11-04T10:30:00Z',
    version: 3,
    closed_at: '2026-11-04T10:30:00Z',
    consent_history: [{ scope: 'internal', recorded_at: '2026-11-04T10:20:00Z' }],
    status: 'completed',
    consent: { scope: 'internal', recorded_at: '2026-11-04T10:20:00Z' },
    language: 'en',
    entity_type: 'cooperative',
    summary_original: 'Heavy rain hurt the harvest',
    summary_english: null,
    tags: ['climate and weather'],
    evidence: 'full',
    earlier_answers: [],
    decision_log: [{ at: '2026-11-04T10:15:00Z', kind: 'tool', code: 'tool_called', refs: ['get_producer_record'] }],
    insights: [],
    peer_examples: [],
    feedback: null,
    pii_flag: false,
    pii_review: null,
    review_status: 'pending',
    reviewed_by: null,
    reviewed_at: null,
    reviewer_tags: null,
    reviewer_summary_original: null,
    reviewer_summary_english: null,
    ...overrides,
  } as StoredRecord;
}

class MemoryRecordStore implements RecordStore {
  items = new Map<string, StoredRecord>();
  writes: Array<{ record: StoredRecord; expectedVersion: number }> = [];
  add(...records: StoredRecord[]) {
    for (const r of records) this.items.set(String(r.record_id), r);
  }
  async listClosedCompleted() {
    return [...this.items.values()].filter((r) => r.status === 'completed' && typeof r.closed_at === 'string');
  }
  async listClosedByProducer(producerId: string) {
    return [...this.items.values()].filter(
      (r) => r.producer_id === producerId && typeof r.closed_at === 'string',
    );
  }
  async get(id: string) {
    return this.items.get(id);
  }
  async replace(next: StoredRecord, expectedVersion: number) {
    const current = this.items.get(String(next.record_id));
    // Same condition as DynamoRecordStore: version matches, closed, review still pending
    if (!current || current.version !== expectedVersion || typeof current.closed_at !== 'string' ||
      current.review_status !== 'pending') {
      throw new VersionConflict(current?.version as number | undefined);
    }
    this.writes.push({ record: next, expectedVersion });
    this.items.set(String(next.record_id), next);
  }
}

const reviewer: Identity = { userId: 'reviewer-1', roles: ['reviewer'] };

function setup(identity: Identity | 'reject' = reviewer) {
  const store = new MemoryRecordStore();
  const log = new CaptureLog();
  const resolve: IdentityFullResolver = () => {
    if (identity === 'reject') throw new Unauthorized();
    return identity;
  };
  const handlers = createReviewHandlers(() => ({ store, log, now: () => NOW }), resolve);
  return { store, log, handlers };
}

function event(opts: { id?: string; body?: unknown; query?: Record<string, string> } = {}): APIGatewayProxyEvent {
  return {
    body: opts.body === undefined ? null : JSON.stringify(opts.body),
    pathParameters: opts.id ? { id: opts.id } : null,
    queryStringParameters: opts.query ?? null,
    requestContext: {},
  } as unknown as APIGatewayProxyEvent;
}

const parse = (r: { body: string }) => JSON.parse(r.body);

describe('access', () => {
  it('returns 401 on every route when the identity is rejected', async () => {
    const { handlers } = setup('reject');
    for (const call of [
      handlers.list(event()),
      handlers.get(event({ id: ID(1) })),
      handlers.patch(event({ id: ID(1), body: { version: 1, pii_review: 'cleared' } })),
      handlers.approve(event({ id: ID(1), body: { version: 1 } })),
    ]) {
      expect((await call).statusCode).toBe(401);
    }
  });

  it('returns 403 on every route when the caller has no reviewer role', async () => {
    for (const roles of [['producer'], ['admin'], []] as Identity['roles'][]) {
      const { handlers, store } = setup({ userId: 'u', roles, producerId: 'producer-a' });
      store.add(record(1));
      for (const call of [
        handlers.list(event()),
        handlers.get(event({ id: ID(1) })),
        handlers.patch(event({ id: ID(1), body: { version: 3, pii_review: 'cleared' } })),
        handlers.approve(event({ id: ID(1), body: { version: 3 } })),
      ]) {
        expect((await call).statusCode).toBe(403);
      }
      expect(store.writes).toEqual([]);
    }
  });
});

describe('GET /records', () => {
  it('lists only closed completed records, newest closed first, with effective tags', async () => {
    const { handlers, store } = setup();
    store.add(
      record(1, { closed_at: '2026-11-04T10:30:00Z' }),
      record(2, { closed_at: '2026-11-04T12:00:00Z', reviewer_tags: ['water'] }),
      record(3, { closed_at: null }),
      { record_id: ID(4), status: 'declined', closed_at: '2026-11-04T11:00:00Z' } as StoredRecord,
    );
    const res = await handlers.list(event());
    expect(res.statusCode).toBe(200);
    const { records } = parse(res);
    expect(records.map((r: { record_id: string }) => r.record_id)).toEqual([ID(2), ID(1)]);
    expect(records[0]).toMatchObject({ tags: ['water'], review_status: 'pending', evidence: 'full', version: 3 });
    expect(records[1].tags).toEqual(['climate and weather']);
    expect(records[0]).not.toHaveProperty('summary_original');
  });

  it('filters by review_status and evidence', async () => {
    const { handlers, store } = setup();
    store.add(
      record(1),
      record(2, { review_status: 'reviewed' }),
      record(3, { evidence: 'limited' }),
    );
    const ids = async (query: Record<string, string>) =>
      parse(await handlers.list(event({ query }))).records.map((r: { record_id: string }) => r.record_id).sort();
    expect(await ids({ review_status: 'reviewed' })).toEqual([ID(2)]);
    expect(await ids({ review_status: 'pending' })).toEqual([ID(1), ID(3)]);
    expect(await ids({ evidence: 'limited' })).toEqual([ID(3)]);
  });

  it('pii=unresolved excludes records whose flag was confirmed or cleared; pii=any does not', async () => {
    const { handlers, store } = setup();
    store.add(
      record(1, { pii_flag: true }),
      record(2, { pii_flag: true, pii_review: 'confirmed' }),
      record(3, { pii_flag: true, pii_review: 'cleared' }),
      record(4, { pii_flag: false }),
    );
    const ids = async (pii: string) =>
      parse(await handlers.list(event({ query: { pii } }))).records.map((r: { record_id: string }) => r.record_id).sort();
    expect(await ids('unresolved')).toEqual([ID(1)]);
    expect(await ids('any')).toEqual([ID(1), ID(2), ID(3)]);
  });

  it('rejects unknown filter values with 400', async () => {
    const { handlers } = setup();
    expect((await handlers.list(event({ query: { review_status: 'nope' } }))).statusCode).toBe(400);
    expect((await handlers.list(event({ query: { pii: 'maybe' } }))).statusCode).toBe(400);
  });
});

describe('GET /records/{id}', () => {
  it('returns the full record', async () => {
    const { handlers, store } = setup();
    store.add(record(1));
    const res = await handlers.get(event({ id: ID(1) }));
    expect(res.statusCode).toBe(200);
    expect(parse(res)).toMatchObject({ record_id: ID(1), summary_original: 'Heavy rain hurt the harvest' });
  });

  it('returns 404 for missing, open, declined and malformed IDs', async () => {
    const { handlers, store } = setup();
    store.add(
      record(2, { closed_at: null }),
      { record_id: ID(3), status: 'declined', closed_at: '2026-11-04T11:00:00Z' } as StoredRecord,
    );
    for (const id of [ID(1), ID(2), ID(3), 'not-a-uuid']) {
      expect((await handlers.get(event({ id }))).statusCode).toBe(404);
    }
  });
});

describe('PATCH /records/{id}', () => {
  it('writes only reviewer fields, leaves the agent fields alone, and bumps version and updated_at', async () => {
    const { handlers, store } = setup();
    const before = record(1);
    store.add(before);
    const res = await handlers.patch(
      event({
        id: ID(1),
        body: { version: 3, reviewer_tags: ['water'], reviewer_summary_original: 'Corrected summary' },
      }),
    );
    expect(res.statusCode).toBe(200);
    const after = store.items.get(ID(1))!;
    expect(after).toMatchObject({
      reviewer_tags: ['water'],
      reviewer_summary_original: 'Corrected summary',
      version: 4,
      updated_at: '2026-11-05T09:00:00.000Z',
      review_status: 'pending',
    });
    const changed = Object.keys(after).filter((k) => JSON.stringify(after[k]) !== JSON.stringify(before[k]));
    expect(changed.sort()).toEqual(['reviewer_summary_original', 'reviewer_tags', 'updated_at', 'version']);
    expect(store.writes[0]!.expectedVersion).toBe(3);
    expect(parse(res).version).toBe(4);
  });

  it('records the PII decision', async () => {
    const { handlers, store } = setup();
    store.add(record(1, { pii_flag: true }));
    await handlers.patch(event({ id: ID(1), body: { version: 3, pii_review: 'confirmed' } }));
    expect(store.items.get(ID(1))!.pii_review).toBe('confirmed');
  });

  it('returns 409 with the current version when the version is stale', async () => {
    const { handlers, store } = setup();
    store.add(record(1));
    const res = await handlers.patch(event({ id: ID(1), body: { version: 2, reviewer_tags: ['water'] } }));
    expect(res.statusCode).toBe(409);
    expect(parse(res)).toMatchObject({ reason: 'version_conflict', currentVersion: 3 });
    expect(store.writes).toEqual([]);
  });

  it('returns 409 when the store reports a lost race', async () => {
    const { handlers, store } = setup();
    store.add(record(1));
    const realReplace = store.replace.bind(store);
    store.replace = async (next, expected) => {
      store.items.set(ID(1), record(1, { version: 4 })); // another writer got in first
      return realReplace(next, expected);
    };
    const res = await handlers.patch(event({ id: ID(1), body: { version: 3, reviewer_tags: ['water'] } }));
    expect(res.statusCode).toBe(409);
    expect(parse(res)).toMatchObject({ reason: 'version_conflict', currentVersion: 4 });
  });

  it('fails schema validation for an invalid tag, without writing', async () => {
    const { handlers, store } = setup();
    store.add(record(1));
    const res = await handlers.patch(event({ id: ID(1), body: { version: 3, reviewer_tags: ['astrology'] } }));
    expect(res.statusCode).toBe(400);
    expect(store.writes).toEqual([]);
  });

  it('rejects fields a reviewer may not change, and IDs in the body, with 400', async () => {
    const { handlers, store } = setup();
    store.add(record(1));
    for (const body of [
      { version: 3, tags: ['water'] },
      { version: 3, summary_original: 'x' },
      { version: 3, review_status: 'reviewed' },
      { version: 3, producer_id: 'someone-else' },
      { version: 3 },
      { reviewer_tags: ['water'] },
      { version: '3', reviewer_tags: ['water'] },
    ]) {
      expect((await handlers.patch(event({ id: ID(1), body }))).statusCode, JSON.stringify(body)).toBe(400);
    }
    expect(store.writes).toEqual([]);
  });

  it('returns 404 for an open or declined record', async () => {
    const { handlers, store } = setup();
    store.add(record(1, { closed_at: null }));
    expect((await handlers.patch(event({ id: ID(1), body: { version: 3, reviewer_tags: ['water'] } }))).statusCode).toBe(404);
  });
});

describe('POST /records/{id}/approve', () => {
  it('sets the review fields from the caller and the clock', async () => {
    const { handlers, store } = setup();
    store.add(record(1));
    const res = await handlers.approve(event({ id: ID(1), body: { version: 3 } }));
    expect(res.statusCode).toBe(200);
    expect(store.items.get(ID(1))).toMatchObject({
      review_status: 'reviewed',
      reviewed_by: 'reviewer-1',
      reviewed_at: '2026-11-05T09:00:00.000Z',
      version: 4,
    });
  });

  it('returns 409 pii_unresolved when the PII flag has no decision', async () => {
    const { handlers, store } = setup();
    store.add(record(1, { pii_flag: true }));
    const res = await handlers.approve(event({ id: ID(1), body: { version: 3 } }));
    expect(res.statusCode).toBe(409);
    expect(parse(res).reason).toBe('pii_unresolved');
    expect(store.items.get(ID(1))!.review_status).toBe('pending');
  });

  it('approves a flagged record once the PII decision is made', async () => {
    const { handlers, store } = setup();
    store.add(record(1, { pii_flag: true }));
    await handlers.patch(event({ id: ID(1), body: { version: 3, pii_review: 'cleared' } }));
    const res = await handlers.approve(event({ id: ID(1), body: { version: 4 } }));
    expect(res.statusCode).toBe(200);
    expect(store.items.get(ID(1))!.review_status).toBe('reviewed');
  });

  it('returns 409 on a stale version', async () => {
    const { handlers, store } = setup();
    store.add(record(1));
    const res = await handlers.approve(event({ id: ID(1), body: { version: 1 } }));
    expect(res.statusCode).toBe(409);
    expect(parse(res)).toMatchObject({ reason: 'version_conflict', currentVersion: 3 });
  });
});

describe('after approval', () => {
  it('PATCH and a second approve return 409 and change nothing', async () => {
    const { handlers, store } = setup();
    store.add(record(1));
    await handlers.approve(event({ id: ID(1), body: { version: 3 } }));
    const approved = store.items.get(ID(1));

    const patched = await handlers.patch(event({ id: ID(1), body: { version: 4, reviewer_tags: ['water'] } }));
    expect(patched.statusCode).toBe(409);
    expect(parse(patched).reason).toBe('approved');
    expect((await handlers.approve(event({ id: ID(1), body: { version: 4 } }))).statusCode).toBe(409);
    expect(store.items.get(ID(1))).toBe(approved);
  });
});

describe('logging and unexpected errors', () => {
  it('logs record ID, reviewer, route and status only, never narrative text', async () => {
    const { handlers, store, log } = setup();
    store.add(record(1));
    await handlers.patch(event({ id: ID(1), body: { version: 3, reviewer_summary_original: 'Secret farmer words' } }));
    const logged = log.lines.join('\n');
    expect(logged).toContain(ID(1));
    expect(logged).toContain('reviewer-1');
    expect(logged).toContain('PATCH /records/{id}');
    expect(logged).not.toContain('Secret farmer words');
    expect(logged).not.toContain('Heavy rain');
  });

  it('returns a bare 500 for an unexpected failure', async () => {
    const { handlers, store } = setup();
    store.listClosedCompleted = async () => {
      throw new Error('table exploded: Heavy rain');
    };
    const res = await handlers.list(event());
    expect(res.statusCode).toBe(500);
    expect(res.body).not.toContain('exploded');
  });
});

describe('record schema validation', () => {
  it('accepts a valid record and rejects an unknown field', () => {
    expect(validateRecord(record(1))).toBeUndefined();
    expect(validateRecord({ ...record(1), surprise: true })).toBeDefined();
  });
});
