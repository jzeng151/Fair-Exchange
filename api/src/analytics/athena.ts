import {
  BatchGetNamedQueryCommand,
  GetQueryExecutionCommand,
  GetQueryResultsCommand,
  StartQueryExecutionCommand,
  StopQueryExecutionCommand,
  type AthenaClient,
} from '@aws-sdk/client-athena';
import type { Log } from '../core/types.js';

/**
 * Runs the Analytics API's fixed Athena queries (#29 spec).
 *
 * The SQL is defined once, as Athena named queries in CDK (`infra/lib/analytics-queries-stack.ts`).
 * The handler loads it by ID and matches it by name. These names and the result columns are the
 * contract with that stack; change both together.
 */
export const QUERY_NAMES = {
  liveBreakdowns: 'analytics-live-breakdowns',
  liveFootprint: 'analytics-live-ai-footprint',
  seededBreakdowns: 'analytics-seeded-breakdowns',
  seededFootprint: 'analytics-seeded-ai-footprint',
} as const;

export type QueryName = (typeof QUERY_NAMES)[keyof typeof QUERY_NAMES];

/** All queries together, including loading the named queries, must finish within this. */
export const ANALYTICS_TIMEOUT_MS = 20_000;
/** Cleanup after a failure or timeout is best effort and bounded, so a stalled Athena can't hold the response. */
export const CANCEL_GRACE_MS = 1_000;
export const POLL_MS = 250;

/** Any query failed or timed out. The route returns 503 and nothing partial. */
export class AnalyticsUnavailable extends Error {
  constructor(reason: string) {
    super(reason);
    this.name = 'AnalyticsUnavailable';
  }
}

export interface AthenaDeps {
  athena: AthenaClient;
  workGroup: string;
  /** Named query IDs (the AnalyticsNamedQueryIds stack output). */
  namedQueryIds: string[];
  timeoutMs: number;
  pollMs: number;
  /** How long to wait for Athena to accept the stop requests after a failure (default CANCEL_GRACE_MS). */
  cancelGraceMs?: number;
  log: Log;
}

/** One result row, by column name. */
export type Row = Record<string, string | undefined>;
export type QueryResults = Record<QueryName, Row[]>;

const NAMES = Object.values(QUERY_NAMES);

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => (clearTimeout(t), resolve()), { once: true });
  });

/** Loads the named queries' SQL. Cached per handler instance by the caller. */
export async function loadNamedQueries(d: AthenaDeps, signal?: AbortSignal): Promise<Record<QueryName, string>> {
  const out = await d.athena.send(new BatchGetNamedQueryCommand({ NamedQueryIds: d.namedQueryIds }), {
    abortSignal: signal,
  });
  const byName = new Map((out.NamedQueries ?? []).map((q) => [q.Name, q.QueryString]));
  const sql = {} as Record<QueryName, string>;
  for (const name of NAMES) {
    const q = byName.get(name);
    if (!q) throw new AnalyticsUnavailable(`named query missing: ${name}`);
    sql[name] = q;
  }
  return sql;
}

async function readAll(d: AthenaDeps, id: string, signal: AbortSignal): Promise<Row[]> {
  const rows: Row[] = [];
  let columns: string[] | undefined;
  let token: string | undefined;
  let first = true;
  do {
    const page = await d.athena.send(new GetQueryResultsCommand({ QueryExecutionId: id, NextToken: token }), {
      abortSignal: signal,
    });
    columns ??= (page.ResultSet?.ResultSetMetadata?.ColumnInfo ?? []).map((c) => c.Name ?? '');
    const data = page.ResultSet?.Rows ?? [];
    // The first row of the first page is the header.
    for (const r of first ? data.slice(1) : data) {
      rows.push(Object.fromEntries(columns.map((c, i) => [c, r.Data?.[i]?.VarCharValue])));
    }
    first = false;
    token = page.NextToken;
  } while (token);
  return rows;
}

/**
 * Loads the SQL (unless given), then starts every query at once and waits for all of them.
 * Throws AnalyticsUnavailable if any fails or the time limit passes; unfinished queries are stopped.
 */
export async function runAnalyticsQueries(
  d: AthenaDeps,
  getSql: (signal: AbortSignal) => Promise<Record<QueryName, string>>,
): Promise<QueryResults> {
  const controller = new AbortController();
  const { signal } = controller;
  const running = new Set<string>();

  const runOne = async (sql: string): Promise<Row[]> => {
    const { QueryExecutionId: id } = await d.athena.send(
      new StartQueryExecutionCommand({ QueryString: sql, WorkGroup: d.workGroup }),
      { abortSignal: signal },
    );
    if (!id) throw new AnalyticsUnavailable('query did not start');
    running.add(id);
    for (;;) {
      if (signal.aborted) throw new AnalyticsUnavailable('aborted');
      const out = await d.athena.send(new GetQueryExecutionCommand({ QueryExecutionId: id }), {
        abortSignal: signal,
      });
      const state = out.QueryExecution?.Status?.State;
      if (state === 'SUCCEEDED') break;
      if (state === 'FAILED' || state === 'CANCELLED') throw new AnalyticsUnavailable(`query ${state}`);
      await sleep(d.pollMs, signal);
    }
    running.delete(id);
    return readAll(d, id, signal);
  };

  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new AnalyticsUnavailable('timed out')), d.timeoutMs);
  });
  const work = (async () => {
    const sql = await getSql(signal);
    const rows = await Promise.all(NAMES.map((name) => runOne(sql[name])));
    return Object.fromEntries(NAMES.map((name, i) => [name, rows[i]!])) as QueryResults;
  })();
  work.catch(() => undefined); // settled via the race below

  try {
    return await Promise.race([work, deadline]);
  } catch (err) {
    const reason = err instanceof Error ? err.message : 'unknown';
    d.log.warn('analytics queries unavailable', { reason, error: err instanceof Error ? err.name : 'unknown' });
    throw err instanceof AnalyticsUnavailable ? err : new AnalyticsUnavailable(reason);
  } finally {
    clearTimeout(timer);
    controller.abort();
    // Best effort: stop anything still running so no query outlives the request, but never wait longer
    // than the grace period for Athena to accept the stops (a stalled Athena must not hold the 503).
    const stops = Promise.allSettled(
      [...running].map((id) => d.athena.send(new StopQueryExecutionCommand({ QueryExecutionId: id }))),
    );
    let grace: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([
      stops,
      new Promise<void>((resolve) => { grace = setTimeout(resolve, d.cancelGraceMs ?? CANCEL_GRACE_MS); }),
    ]);
    clearTimeout(grace);
  }
}
