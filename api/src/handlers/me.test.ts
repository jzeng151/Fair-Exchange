import type { APIGatewayProxyEvent } from 'aws-lambda';
import { describe, expect, it } from 'vitest';
import { Unauthorized, type Identity, type IdentityFullResolver } from '../core/identity.js';
import type { RecordStore, StoredRecord } from '../core/reviewStore.js';
import { CaptureLog } from '../core/testing.js';
import { createMeHandlers } from './me.js';

/** Seam 2 (#32): the real handler, a fake identity resolver and an in-memory record store. */

const ID = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

function completed(n: number, overrides: Record<string, unknown> = {}): StoredRecord {
  return {
    record_id: ID(n),
    producer_id: 'producer-a',
    created_at: '2026-11-04T10:00:00Z',
    source: 'agent conversation',
    updated_at: '2026-11-04T10:30:00Z',
    version: 3,
    closed_at: '2026-11-04T10:30:00Z',
    status: 'completed',
    consent: { scope: 'internal', recorded_at: '2026-11-04T10:20:00Z' },
    consent_history: [{ scope: 'internal', recorded_at: '2026-11-04T10:20:00Z' }],
    language: 'en',
    entity_type: 'cooperative',
    summary_original: 'Heavy rain hurt the harvest',
    summary_english: null,
    tags: ['climate and weather'],
    evidence: 'full',
    earlier_answers: [],
    insights: [{ text: 'Rainfall fell 20%', citation: { source: 'CHIRPS', standard_clause: 'APS 1.1' } }],
    peer_examples: [],
    feedback: 'yes',
    pii_flag: true,
    pii_review: 'confirmed',
    review_status: 'pending',
    reviewed_by: null,
    reviewed_at: null,
    reviewer_tags: null,
    reviewer_summary_original: null,
    reviewer_summary_english: null,
    ...overrides,
  } as StoredRecord;
}

function declined(n: number, overrides: Record<string, unknown> = {}): StoredRecord {
  return {
    record_id: ID(n),
    producer_id: 'producer-a',
    created_at: '2026-11-04T11:00:00Z',
    source: 'agent conversation',
    updated_at: '2026-11-04T11:10:00Z',
    version: 1,
    closed_at: '2026-11-04T11:10:00Z',
    status: 'declined',
    consent: { scope: 'declined', recorded_at: '2026-11-04T11:05:00Z' },
    ...overrides,
  } as StoredRecord;
}

class MemoryRecordStore implements RecordStore {
  items = new Map<string, StoredRecord>();
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
  async replace() {
    throw new Error('not used');
  }
}

const producerA: Identity = { userId: 'u-a', roles: ['producer'], producerId: 'producer-a' };

function setup(identity: Identity | 'reject' = producerA) {
  const store = new MemoryRecordStore();
  const log = new CaptureLog();
  const resolve: IdentityFullResolver = () => {
    if (identity === 'reject') throw new Unauthorized();
    return identity;
  };
  const handlers = createMeHandlers(() => ({ store, log }), resolve);
  return { store, log, handlers };
}

const event = (): APIGatewayProxyEvent => ({ requestContext: {} }) as unknown as APIGatewayProxyEvent;

async function list(identity: Identity | 'reject' = producerA, seed?: (s: MemoryRecordStore) => void) {
  const { store, handlers } = setup(identity);
  seed?.(store);
  const r = await handlers.records(event());
  return { statusCode: r.statusCode, body: JSON.parse(r.body) as { records?: Record<string, unknown>[] } };
}

describe('GET /me/records', () => {
  it('returns only the caller’s records, even when others exist', async () => {
    const { body } = await list(producerA, (s) => {
      s.add(completed(1), completed(2, { producer_id: 'producer-b' }), declined(3, { producer_id: 'producer-b' }));
    });
    const ids = body.records!.map((r) => r.record_id);
    expect(ids).toEqual([ID(1)]);
  });

  it('returns 401 for an unidentified caller', async () => {
    expect((await list('reject')).statusCode).toBe(401);
  });

  it('returns 403 for a non-producer', async () => {
    const reviewer: Identity = { userId: 'rev', roles: ['reviewer'] };
    expect((await list(reviewer)).statusCode).toBe(403);
  });

  it('excludes open conversations (no closed_at)', async () => {
    const { body } = await list(producerA, (s) => s.add(completed(1), completed(2, { closed_at: null })));
    expect(body.records!.map((r) => r.record_id)).toEqual([ID(1)]);
  });

  it('shows a declined record as only id, closed time and declined', async () => {
    const { body } = await list(producerA, (s) => s.add(declined(5)));
    expect(body.records).toEqual([
      { record_id: ID(5), closed_at: '2026-11-04T11:10:00Z', status: 'declined' },
    ]);
  });

  it('does not list a record whose outcome is not decided', async () => {
    // A completed-shaped record with no committed consent scope: outcome not decided (#32).
    const undecided = completed(7, { consent: { scope: '', recorded_at: '2026-11-04T10:20:00Z' } });
    const { body } = await list(producerA, (s) => s.add(undecided));
    expect(body.records).toEqual([]);
  });

  it('never returns summary_english, pii_* , the decision log, ai_usage or the reviewer identity', async () => {
    const { body } = await list(producerA, (s) =>
      s.add(
        completed(1, {
          language: 'es',
          summary_english: 'Heavy rain hurt the harvest',
          reviewed_by: 'reviewer-1',
          reviewed_at: '2026-11-05T09:00:00Z',
        }),
      ),
    );
    const rec = body.records![0]!;
    for (const forbidden of [
      'summary_english',
      'pii_flag',
      'pii_review',
      'reviewed_by',
      'reviewed_at',
      'decision_log',
      'ai_usage',
      'producer_id',
    ]) {
      expect(rec).not.toHaveProperty(forbidden);
    }
    expect(rec.summary).toBe('Heavy rain hurt the harvest');
  });

  it('sets changed_by_reviewer when a reviewer value exists and uses it', async () => {
    const { body } = await list(producerA, (s) =>
      s.add(
        completed(1, { reviewer_summary_original: 'Corrected summary', reviewer_tags: ['water'] }),
        completed(2, { record_id: ID(2) }),
      ),
    );
    const byId = Object.fromEntries(body.records!.map((r) => [r.record_id, r]));
    expect(byId[ID(1)]!.changed_by_reviewer).toBe(true);
    expect(byId[ID(1)]!.summary).toBe('Corrected summary');
    expect(byId[ID(1)]!.tags).toEqual(['water']);
    expect(byId[ID(2)]!.changed_by_reviewer).toBe(false);
    expect(byId[ID(2)]!.summary).toBe('Heavy rain hurt the harvest');
  });

  it('returns insights and peer examples with citations', async () => {
    const { body } = await list(producerA, (s) => s.add(completed(1)));
    expect(body.records![0]!.insights).toEqual([
      { text: 'Rainfall fell 20%', citation: { source: 'CHIRPS', standard_clause: 'APS 1.1' } },
    ]);
  });

  it('orders records newest first by closed time', async () => {
    const { body } = await list(producerA, (s) =>
      s.add(
        completed(1, { closed_at: '2026-11-01T10:00:00Z' }),
        completed(2, { closed_at: '2026-11-03T10:00:00Z' }),
        completed(3, { closed_at: '2026-11-02T10:00:00Z' }),
      ),
    );
    expect(body.records!.map((r) => r.record_id)).toEqual([ID(2), ID(3), ID(1)]);
  });
});
