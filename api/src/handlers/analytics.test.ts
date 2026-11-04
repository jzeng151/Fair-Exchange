import {
  AthenaClient,
  BatchGetNamedQueryCommand,
  GetQueryExecutionCommand,
  GetQueryResultsCommand,
  StartQueryExecutionCommand,
  StopQueryExecutionCommand,
  type ResultSet,
} from '@aws-sdk/client-athena';
import type { APIGatewayProxyEvent, APIGatewayProxyResult } from 'aws-lambda';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it } from 'vitest';
import { QUERY_NAMES } from '../analytics/athena.js';
import { Unauthorized, type Identity, type IdentityFullResolver } from '../core/identity.js';
import { CaptureLog } from '../core/testing.js';
import { createAnalyticsHandler, type AnalyticsDeps } from './analytics.js';

/**
 * Seam 2 (#29 spec): the Lambda handler with the Athena client mocked and a fake identity resolver.
 * Count fixtures give each cell as [reviewed, all], where all = reviewed + pending.
 */

type Counts = Record<string, Record<string, [number, number]>>;
type Usage = [string, number, number][];

const athena = mockClient(AthenaClient);

const ADMIN: Identity = { userId: 'admin-1', roles: ['admin'] };
const fakeResolver =
  (identity: Identity | null): IdentityFullResolver =>
  () => {
    if (!identity) throw new Unauthorized();
    return identity;
  };

const event = (query: Record<string, string> | null = null): APIGatewayProxyEvent =>
  ({ queryStringParameters: query, requestContext: {} }) as unknown as APIGatewayProxyEvent;

const SQL: Record<string, string> = Object.fromEntries(
  Object.values(QUERY_NAMES).map((name) => [name, `-- sql for ${name}`]),
);
const IDS = Object.values(QUERY_NAMES).map((name) => `id-${name}`);

function countResult(counts: Counts): ResultSet {
  const header = ['breakdown', 'cell', 'reviewed_count', 'all_count'];
  const rows = Object.entries(counts).flatMap(([b, cells]) =>
    Object.entries(cells).map(([c, [r, a]]) => [b, c, String(r), String(a)]),
  );
  return toResultSet(header, rows);
}

function usageResult(usage: Usage): ResultSet {
  return toResultSet(
    ['model_id', 'input_tokens', 'output_tokens'],
    usage.map(([m, i, o]) => [m, String(i), String(o)]),
  );
}

function toResultSet(header: string[], rows: string[][]): ResultSet {
  return {
    ResultSetMetadata: { ColumnInfo: header.map((Name) => ({ Name, Type: 'varchar' })) },
    Rows: [header, ...rows].map((r) => ({ Data: r.map((VarCharValue) => ({ VarCharValue })) })),
  };
}

interface Fixture {
  live?: Counts;
  seeded?: Counts;
  liveUsage?: Usage;
  seededUsage?: Usage;
  /** Query name whose execution fails, or hangs forever. */
  fail?: string;
  hang?: string;
}

/** Wires the mocked Athena client: named queries, then one execution per query name. */
function given(f: Fixture) {
  athena.reset();
  athena.on(BatchGetNamedQueryCommand).resolves({
    NamedQueries: Object.entries(SQL).map(([Name, QueryString]) => ({
      Name,
      QueryString,
      Database: 'fex',
      NamedQueryId: `id-${Name}`,
    })),
    UnprocessedNamedQueryIds: [],
  });
  athena.on(StartQueryExecutionCommand).callsFake((input: { QueryString: string }) => {
    const name = Object.entries(SQL).find(([, sql]) => sql === input.QueryString)![0];
    return { QueryExecutionId: `exec-${name}` };
  });
  athena.on(GetQueryExecutionCommand).callsFake((input: { QueryExecutionId: string }) => {
    const name = input.QueryExecutionId.replace(/^exec-/, '');
    const State = name === f.hang ? 'RUNNING' : name === f.fail ? 'FAILED' : 'SUCCEEDED';
    return { QueryExecution: { QueryExecutionId: input.QueryExecutionId, Status: { State } } };
  });
  athena.on(GetQueryResultsCommand).callsFake((input: { QueryExecutionId: string }) => {
    const name = input.QueryExecutionId.replace(/^exec-/, '');
    const results: Record<string, ResultSet> = {
      [QUERY_NAMES.liveBreakdowns]: countResult(f.live ?? {}),
      [QUERY_NAMES.seededBreakdowns]: countResult(f.seeded ?? {}),
      [QUERY_NAMES.liveFootprint]: usageResult(f.liveUsage ?? []),
      [QUERY_NAMES.seededFootprint]: usageResult(f.seededUsage ?? []),
    };
    return { ResultSet: results[name] };
  });
  athena.on(StopQueryExecutionCommand).resolves({});
}

function deps(overrides: Partial<AnalyticsDeps> = {}): AnalyticsDeps {
  return {
    athena: new AthenaClient({ region: 'us-west-2' }),
    workGroup: 'fex',
    namedQueryIds: IDS,
    timeoutMs: 20_000,
    pollMs: 1,
    log: new CaptureLog(),
    ...overrides,
  };
}

async function call(
  opts: { identity?: Identity | null; query?: Record<string, string> | null; deps?: Partial<AnalyticsDeps> } = {},
): Promise<{ status: number; body: any }> {
  const d = deps(opts.deps);
  const h = createAnalyticsHandler(() => d, fakeResolver(opts.identity === undefined ? ADMIN : opts.identity));
  const r = (await h(event(opts.query ?? null))) as APIGatewayProxyResult;
  return { status: r.statusCode, body: JSON.parse(r.body) };
}

/** Both views, as the two responses an admin could compare. */
async function bothViews(f: Fixture) {
  given(f);
  const reviewed = await call();
  given(f);
  const pending = await call({ query: { include_pending: 'true' } });
  expect(reviewed.status).toBe(200);
  expect(pending.status).toBe(200);
  return { reviewed: reviewed.body, pending: pending.body };
}

const S = { suppressed: true };

/** A healthy base so only the cells under test are near the limits. */
const BASE: Counts = {
  participation: { completed: [40, 50], declined: [20, 20] },
  language: { en: [20, 25], es: [20, 25] },
};

beforeEach(() => athena.reset());

describe('access', () => {
  it('returns 403 for a caller without the admin role', async () => {
    for (const roles of [['producer'], ['reviewer'], []] as Identity['roles'][]) {
      given({ live: BASE });
      const r = await call({ identity: { userId: 'u', roles } });
      expect(r.status).toBe(403);
      expect(r.body).toEqual({ message: 'Forbidden' });
    }
    expect(athena.commandCalls(StartQueryExecutionCommand)).toHaveLength(0);
  });

  it('returns 401 when the identity is rejected', async () => {
    given({ live: BASE });
    expect((await call({ identity: null })).status).toBe(401);
  });

  it('returns 200 for an admin', async () => {
    given({ live: BASE });
    expect((await call()).status).toBe(200);
  });
});

describe('queries', () => {
  it('runs every named query in the workgroup, using the SQL loaded by ID', async () => {
    given({ live: BASE });
    await call();
    const batch = athena.commandCalls(BatchGetNamedQueryCommand)[0]!.args[0].input;
    expect(batch.NamedQueryIds).toEqual(IDS);
    const started = athena.commandCalls(StartQueryExecutionCommand).map((c) => c.args[0].input);
    expect(started.map((i) => i.QueryString).sort()).toEqual(Object.values(SQL).sort());
    expect(started.every((i) => i.WorkGroup === 'fex')).toBe(true);
  });

  it('starts all queries before waiting on any (parallel)', async () => {
    given({ live: BASE });
    const order: string[] = [];
    athena.on(StartQueryExecutionCommand).callsFake((input: { QueryString: string }) => {
      order.push('start');
      const name = Object.entries(SQL).find(([, sql]) => sql === input.QueryString)![0];
      return { QueryExecutionId: `exec-${name}` };
    });
    athena.on(GetQueryExecutionCommand).callsFake((input: { QueryExecutionId: string }) => {
      order.push('poll');
      return { QueryExecution: { QueryExecutionId: input.QueryExecutionId, Status: { State: 'SUCCEEDED' } } };
    });
    await call();
    expect(order.slice(0, 4)).toEqual(['start', 'start', 'start', 'start']);
  });
});

describe('suppression of live counts', () => {
  it('hides live counts 1 to 4 as {"suppressed": true}', async () => {
    given({ live: { ...BASE, tag: { water: [3, 3], health: [1, 1], soil: [9, 9] } } });
    const { body } = await call();
    expect(body.live.by_tag.water).toEqual(S);
    expect(body.live.by_tag.health).toEqual(S);
    expect(body.live.by_tag.soil).toBe(9);
  });

  it('hides a second cell when a breakdown has exactly one hidden cell', async () => {
    given({ live: { ...BASE, entity_type: { cooperative: [30, 30], smallholder: [2, 2], processor: [7, 7] } } });
    const { body } = await call();
    expect(body.live.by_entity_type).toEqual({ cooperative: 30, smallholder: S, processor: S });
  });

  it('with include_pending, hides a cell whose pending-only count is 1 to 4', async () => {
    given({ live: { ...BASE, evidence: { full: [20, 22], limited: [10, 10] } } });
    const { body } = await call({ query: { include_pending: 'true' } });
    expect(body.live.by_evidence).toEqual({ full: S, limited: S });
  });

  it('reconstruction case: 1 completed (pending) and 5 declined: both hidden in both views', async () => {
    // Declines are never reviewed, so they count in both views (reviewed == all).
    const { reviewed, pending } = await bothViews({
      live: { participation: { completed: [0, 1], declined: [5, 5] } },
    });
    for (const body of [reviewed, pending]) {
      expect(body.live.completed).toEqual(S);
      expect(body.live.declined).toEqual(S);
    }
  });

  it('a pending-only difference of 1 to 4 in the completed count hides both in both views', async () => {
    // A declined count never differs between views (declines are never reviewed), so only completed can.
    for (const participation of [
      { completed: [40, 43], declined: [20, 20] },
      { completed: [12, 14], declined: [30, 30] },
    ] as Counts[string][]) {
      const { reviewed, pending } = await bothViews({ live: { participation } });
      for (const body of [reviewed, pending]) {
        expect(body.live.completed).toEqual(S);
        expect(body.live.declined).toEqual(S);
      }
    }
  });

  it('reconstruction case: reviewed A=1, B=5, five pending added to A: A and B hidden in both views', async () => {
    const { reviewed, pending } = await bothViews({
      live: { ...BASE, tag: { A: [1, 6], B: [5, 5] } },
    });
    expect(reviewed.live.by_tag).toEqual({ A: S, B: S });
    expect(pending.live.by_tag).toEqual({ A: S, B: S });
  });

  it('hides the same cells whichever view is requested', async () => {
    const live: Counts = {
      participation: { completed: [40, 50], declined: [20, 20] },
      language: { en: [10, 10], es: [0, 3], fr: [7, 7] },
      tag: { x: [2, 10], y: [6, 50], z: [40, 45], w: [60, 60] },
    };
    const { reviewed, pending } = await bothViews({ live });
    const hiddenKeys = (b: Record<string, unknown>) =>
      Object.entries(b).filter(([, v]) => typeof v !== 'number').map(([k]) => k).sort();
    for (const breakdown of ['by_language', 'by_tag']) {
      expect(hiddenKeys(reviewed.live[breakdown])).toEqual(hiddenKeys(pending.live[breakdown]));
    }
    expect(hiddenKeys(reviewed.live.by_tag)).toEqual(['x', 'y', 'z']);
  });
});

describe('response contents', () => {
  const FULL: Fixture = {
    live: {
      participation: { completed: [40, 50], declined: [20, 20] },
      tag: { water: [20, 25], health: [20, 25] },
      language: { en: [20, 25], es: [20, 25] },
      entity_type: { cooperative: [40, 50] },
      consent_scope: { internal: [20, 25], internal_and_outward: [20, 25] },
      feedback: { yes: [20, 25], none: [20, 25] },
      evidence: { full: [20, 25], limited: [20, 25] },
    },
    seeded: {
      participation: { completed: [150, 180], declined: [20, 20] },
      tag: { water: [3, 4], health: [60, 70] },
      language: { en: [1, 2], es: [140, 160] },
    },
    liveUsage: [['model-a', 1000, 200], ['model-b', 50, 5]],
    seededUsage: [['model-a', 999_999, 88_888]],
  };

  it('has live and seeded sections, each with every breakdown, plus the filters applied', async () => {
    given(FULL);
    const { body } = await call();
    expect(Object.keys(body).sort()).toEqual(['filters', 'live', 'seeded']);
    const keys = [
      'ai_footprint', 'by_consent_scope', 'by_entity_type', 'by_evidence', 'by_feedback', 'by_language',
      'by_tag', 'completed', 'declined',
    ];
    expect(Object.keys(body.live).sort()).toEqual(keys);
    expect(Object.keys(body.seeded).sort()).toEqual(keys);
    expect(body.filters).toEqual({
      include_pending: false,
      consent_scopes: ['internal', 'internal_and_outward'],
      live_closed_only: true,
    });
  });

  it('excludes pending records by default and includes them only with include_pending=true', async () => {
    given(FULL);
    expect((await call()).body.live.by_language).toEqual({ en: 20, es: 20 });
    given(FULL);
    for (const value of ['false', 'yes', '1', 'TRUE']) {
      given(FULL);
      const r = await call({ query: { include_pending: value } });
      expect(r.body.live.by_language).toEqual({ en: 20, es: 20 });
      expect(r.body.filters.include_pending).toBe(false);
    }
    given(FULL);
    const r = await call({ query: { include_pending: 'true' } });
    expect(r.body.live.by_language).toEqual({ en: 25, es: 25 });
    expect(r.body.filters.include_pending).toBe(true);
  });

  it('returns seeded counts separately, unsuppressed, and never adds them to live cells', async () => {
    given(FULL);
    const { body } = await call();
    expect(body.seeded.completed).toBe(150);
    expect(body.seeded.by_tag).toEqual({ water: 3, health: 60 });
    expect(body.seeded.by_language).toEqual({ en: 1, es: 140 });
    expect(body.seeded.ai_footprint).toEqual([{ model_id: 'model-a', input_tokens: 999_999, output_tokens: 88_888 }]);
    // Live is exactly the live fixture.
    expect(body.live.completed).toBe(40);
    expect(body.live.by_tag).toEqual({ water: 20, health: 20 });
    expect(body.live.by_language).toEqual({ en: 20, es: 20 });
    expect(body.live.ai_footprint).toContainEqual({ model_id: 'model-a', input_tokens: 1000, output_tokens: 200 });
  });

  it('seeded counts do not change which live cells are hidden', async () => {
    const live: Counts = { ...BASE, tag: { water: [3, 3], health: [6, 6], soil: [9, 9] } };
    given({ live });
    const alone = (await call()).body.live;
    given({ live, seeded: { tag: { water: [100, 100], health: [1, 1] } } });
    expect((await call()).body.live).toEqual(alone);
  });

  it('returns no totals anywhere', async () => {
    given(FULL);
    const { body } = await call({ query: { include_pending: 'true' } });
    const keys: string[] = [];
    const walk = (v: unknown) => {
      if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) (keys.push(k), walk(x));
    };
    walk(body);
    expect(keys.filter((k) => /total|sum|overall|^all/i.test(k))).toEqual([]);
    for (const b of ['by_tag', 'by_language', 'by_entity_type', 'by_consent_scope', 'by_feedback', 'by_evidence']) {
      expect(Object.keys(body.live[b]).sort()).toEqual(
        Object.keys(FULL.live![b.replace(/^by_/, '')]!).sort(),
      );
    }
  });

  it('gives the AI footprint as total tokens per model only, with no conversation count or average', async () => {
    given(FULL);
    const { body } = await call();
    expect(body.live.ai_footprint).toEqual([
      { model_id: 'model-a', input_tokens: 1000, output_tokens: 200 },
      { model_id: 'model-b', input_tokens: 50, output_tokens: 5 },
    ]);
    for (const entry of [...body.live.ai_footprint, ...body.seeded.ai_footprint]) {
      expect(Object.keys(entry).sort()).toEqual(['input_tokens', 'model_id', 'output_tokens']);
    }
    expect(JSON.stringify(body)).not.toMatch(/conversation|average|avg|mean|per_/i);
  });

  it('shows declines in the default reviewed-only view, the same as with pending included', async () => {
    const { reviewed, pending } = await bothViews({ live: { participation: { completed: [40, 50], declined: [20, 20] } } });
    expect(reviewed.live.declined).toBe(20);
    expect(pending.live.declined).toBe(20);
  });

  it('shows declined records only as a count', async () => {
    given(FULL);
    const { body } = await call({ query: { include_pending: 'true' } });
    expect(body.live.declined).toBe(20);
    expect(JSON.stringify(body.live).match(/declined/g)).toHaveLength(1);
  });
});

describe('failures', () => {
  it('returns 503 with a retry message and nothing partial when a query times out', async () => {
    given({ live: BASE, hang: QUERY_NAMES.seededFootprint });
    const r = await call({ deps: { timeoutMs: 30 } });
    expect(r.status).toBe(503);
    expect(r.body).toEqual({ message: expect.stringMatching(/retry/i) });
    // The hung query is stopped.
    expect(athena.commandCalls(StopQueryExecutionCommand).map((c) => c.args[0].input.QueryExecutionId)).toContain(
      `exec-${QUERY_NAMES.seededFootprint}`,
    );
  });

  it('returns 503 and nothing partial when any query fails', async () => {
    given({ live: BASE, fail: QUERY_NAMES.liveFootprint });
    const r = await call();
    expect(r.status).toBe(503);
    expect(Object.keys(r.body)).toEqual(['message']);
  });

  it('returns 503 when the named queries cannot be loaded', async () => {
    given({ live: BASE });
    athena.on(BatchGetNamedQueryCommand).rejects(new Error('throttled'));
    expect((await call()).status).toBe(503);
  });

  it('returns 503 when a named query is missing', async () => {
    given({ live: BASE });
    athena.on(BatchGetNamedQueryCommand).resolves({
      NamedQueries: [{ Name: QUERY_NAMES.liveBreakdowns, QueryString: 'x', Database: 'fex' }],
    });
    expect((await call()).status).toBe(503);
  });

  it('has a 20-second limit by default', async () => {
    const { ANALYTICS_TIMEOUT_MS } = await import('../analytics/athena.js');
    expect(ANALYTICS_TIMEOUT_MS).toBe(20_000);
  });
});
