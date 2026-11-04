import { QUERY_NAMES, type QueryResults, type Row } from './athena.js';
import { suppress, type Cell, type CountTable, type SuppressedView } from './suppression.js';

/**
 * Builds the `GET /analytics` response (#29 spec) from the raw query rows.
 * Live counts are suppressed for both views together; seeded counts are returned as their own
 * series, unsuppressed, and never mixed with live ones. No totals.
 */

/** Breakdowns over completed records with granted consent, as named by the breakdowns query. */
export const BREAKDOWNS = ['tag', 'language', 'entity_type', 'consent_scope', 'feedback', 'evidence'] as const;
/** Completed vs declined: one two-cell breakdown under every suppression rule. */
export const PARTICIPATION = 'participation';

export const GRANTED_SCOPES = ['internal', 'internal_and_outward'] as const;

export interface FootprintEntry {
  model_id: string;
  input_tokens: number;
  output_tokens: number;
}

export interface AnalyticsSection {
  completed: Cell;
  declined: Cell;
  by_tag: Record<string, Cell>;
  by_language: Record<string, Cell>;
  by_entity_type: Record<string, Cell>;
  by_consent_scope: Record<string, Cell>;
  by_feedback: Record<string, Cell>;
  by_evidence: Record<string, Cell>;
  ai_footprint: FootprintEntry[];
}

export interface AnalyticsResponse {
  filters: {
    include_pending: boolean;
    consent_scopes: readonly string[];
    live_closed_only: true;
  };
  live: AnalyticsSection;
  seeded: AnalyticsSection;
}

const count = (v: string | undefined): number => {
  const n = Number(v);
  if (v === undefined || !Number.isSafeInteger(n) || n < 0) throw new Error('bad count in query result');
  return n;
};

/** Rows of (breakdown, cell, reviewed_count, all_count) into a table of both views. */
export function toCountTable(rows: Row[]): CountTable {
  // Both participation cells always exist, so if either is hidden the other is too.
  const table: CountTable = {
    [PARTICIPATION]: { completed: { reviewed: 0, all: 0 }, declined: { reviewed: 0, all: 0 } },
  };
  for (const b of BREAKDOWNS) table[b] = {};
  for (const r of rows) {
    const b = r.breakdown;
    if (!b || !(b in table) || r.cell === undefined) continue;
    table[b]![r.cell] = { reviewed: count(r.reviewed_count), all: count(r.all_count) };
  }
  return table;
}

function toFootprint(rows: Row[]): FootprintEntry[] {
  return rows
    .filter((r) => r.model_id)
    .map((r) => ({ model_id: r.model_id!, input_tokens: count(r.input_tokens), output_tokens: count(r.output_tokens) }))
    .sort((a, b) => (a.model_id < b.model_id ? -1 : a.model_id > b.model_id ? 1 : 0));
}

function section(view: SuppressedView, footprint: FootprintEntry[]): AnalyticsSection {
  const p = view[PARTICIPATION] ?? {};
  const b = (name: (typeof BREAKDOWNS)[number]) => view[name] ?? {};
  return {
    completed: p.completed ?? 0,
    declined: p.declined ?? 0,
    by_tag: b('tag'),
    by_language: b('language'),
    by_entity_type: b('entity_type'),
    by_consent_scope: b('consent_scope'),
    by_feedback: b('feedback'),
    by_evidence: b('evidence'),
    ai_footprint: footprint,
  };
}

/** Seeded demo data: the requested view's raw counts, never suppressed and never combined with live. */
function rawView(table: CountTable, includePending: boolean): SuppressedView {
  return Object.fromEntries(
    Object.entries(table).map(([b, cells]) => [
      b,
      Object.fromEntries(Object.entries(cells).map(([k, v]) => [k, includePending ? v.all : v.reviewed])),
    ]),
  );
}

export function buildResponse(results: QueryResults, includePending: boolean): AnalyticsResponse {
  const live = suppress(toCountTable(results[QUERY_NAMES.liveBreakdowns]));
  const seeded = rawView(toCountTable(results[QUERY_NAMES.seededBreakdowns]), includePending);
  return {
    filters: { include_pending: includePending, consent_scopes: GRANTED_SCOPES, live_closed_only: true },
    live: section(includePending ? live.include_pending : live.reviewed, toFootprint(results[QUERY_NAMES.liveFootprint])),
    seeded: section(seeded, toFootprint(results[QUERY_NAMES.seededFootprint])),
  };
}
