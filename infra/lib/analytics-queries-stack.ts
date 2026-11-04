import { CfnOutput, Fn, Stack, type StackProps } from 'aws-cdk-lib';
import * as athena from 'aws-cdk-lib/aws-athena';
import type { Construct } from 'constructs';
import { RECORDS_GLUE_TABLE, SYNC_DATABASE } from './athena-sync-stack';

/**
 * Spec 29: the fixed Athena queries behind `GET /analytics`, as named queries.
 *
 * The SQL lives only here. The analytics Lambda loads it by ID at cold start (BatchGetNamedQuery)
 * from the `AnalyticsNamedQueryIds` output, passed as `ANALYTICS_NAMED_QUERY_IDS`, and matches
 * the queries by NAME. The names and result columns below are the contract with
 * `api/src/analytics/athena.ts`; change both together.
 *
 * Every count query returns both views at once (`reviewed_count` and `all_count`, i.e. reviewed
 * plus pending), because suppression is always computed for both views together. The queries
 * return raw counts: suppression happens in the Lambda, never in SQL.
 */

/** Athena workgroup defined in AthenaSyncStack (spec 28). */
export const ANALYTICS_WORKGROUP = 'fex';

/**
 * Seeded demo records (spec 37) under `records-seeded/`. ASSUMPTION: the Glue table over that prefix is a
 * follow-up to #37 and not defined yet; it must use this name and the live table's columns.
 */
export const SEEDED_GLUE_TABLE = 'records_seeded';

export const ANALYTICS_QUERY_NAMES = {
  liveBreakdowns: 'analytics-live-breakdowns',
  liveFootprint: 'analytics-live-ai-footprint',
  seededBreakdowns: 'analytics-seeded-breakdowns',
  seededFootprint: 'analytics-seeded-ai-footprint',
} as const;

const GRANTED = `('internal', 'internal_and_outward')`;

/**
 * Columns: breakdown, cell, reviewed_count, all_count.
 * - `participation`: completed records with granted consent vs declined records (count only).
 * - Every other breakdown is over completed records with granted consent.
 * - Effective tags are the reviewer's if set, else the agent's (spec 26).
 * - A record counts as reviewed only when review_status = 'reviewed'. Declined records have no
 *   review status, so they are pending and appear only with include_pending.
 * - Live counts only include closed records (`closed_at` set); `closedOnly` is false for seeded.
 */
export function breakdownsQuery(table: string, closedOnly: boolean): string {
  const where = closedOnly ? 'WHERE closed_at IS NOT NULL' : '';
  return `WITH base AS (
  SELECT
    status,
    consent.scope AS consent_scope,
    language,
    entity_type,
    COALESCE(feedback, 'none') AS feedback,
    evidence,
    array_distinct(COALESCE(reviewer_tags, tags)) AS effective_tags,
    COALESCE(review_status, 'pending') = 'reviewed' AS reviewed
  FROM ${SYNC_DATABASE}.${table}
  ${where}
),
completed AS (
  SELECT * FROM base WHERE status = 'completed' AND consent_scope IN ${GRANTED}
)
SELECT 'participation' AS breakdown, status AS cell, COUNT_IF(reviewed) AS reviewed_count, COUNT(*) AS all_count
FROM base
WHERE (status = 'completed' AND consent_scope IN ${GRANTED}) OR status = 'declined'
GROUP BY status
UNION ALL
SELECT 'tag', tag, COUNT_IF(reviewed), COUNT(*) FROM completed CROSS JOIN UNNEST(effective_tags) AS t (tag) GROUP BY tag
UNION ALL
SELECT 'language', language, COUNT_IF(reviewed), COUNT(*) FROM completed GROUP BY language
UNION ALL
SELECT 'entity_type', entity_type, COUNT_IF(reviewed), COUNT(*) FROM completed GROUP BY entity_type
UNION ALL
SELECT 'consent_scope', consent_scope, COUNT_IF(reviewed), COUNT(*) FROM completed GROUP BY consent_scope
UNION ALL
SELECT 'feedback', feedback, COUNT_IF(reviewed), COUNT(*) FROM completed GROUP BY feedback
UNION ALL
SELECT 'evidence', evidence, COUNT_IF(reviewed), COUNT(*) FROM completed GROUP BY evidence`;
}

/**
 * Columns: model_id, input_tokens, output_tokens. Total tokens per model only: no conversation
 * count or per-conversation average, which could reveal a hidden count. Covers every record
 * (completed and declined; ai_usage is non-narrative), independent of review status.
 */
export function footprintQuery(table: string, closedOnly: boolean): string {
  const where = closedOnly ? 'WHERE closed_at IS NOT NULL' : '';
  return `SELECT u.model_id, SUM(u.input_tokens) AS input_tokens, SUM(u.output_tokens) AS output_tokens
FROM ${SYNC_DATABASE}.${table}
CROSS JOIN UNNEST(ai_usage) AS u (model_id, input_tokens, output_tokens)
${where}
GROUP BY u.model_id`;
}

export class AnalyticsQueriesStack extends Stack {
  constructor(scope: Construct, id: string, props: StackProps = {}) {
    super(scope, id, props);

    const queries: [string, string, string, string][] = [
      ['LiveBreakdowns', ANALYTICS_QUERY_NAMES.liveBreakdowns,
        'Spec 29: live breakdown counts (both views); closed records only. Raw: suppressed by the Lambda.',
        breakdownsQuery(RECORDS_GLUE_TABLE, true)],
      ['LiveFootprint', ANALYTICS_QUERY_NAMES.liveFootprint,
        'Spec 29: live AI footprint, total tokens per model only.', footprintQuery(RECORDS_GLUE_TABLE, true)],
      ['SeededBreakdowns', ANALYTICS_QUERY_NAMES.seededBreakdowns,
        'Spec 29/37: seeded demo breakdown counts, returned separately from live.',
        breakdownsQuery(SEEDED_GLUE_TABLE, false)],
      ['SeededFootprint', ANALYTICS_QUERY_NAMES.seededFootprint,
        'Spec 29/37: seeded demo AI footprint.', footprintQuery(SEEDED_GLUE_TABLE, false)],
    ];
    const ids = queries.map(([logicalId, name, description, queryString]) =>
      new athena.CfnNamedQuery(this, logicalId, {
        name, description, database: SYNC_DATABASE, workGroup: ANALYTICS_WORKGROUP, queryString,
      }).attrNamedQueryId);

    new CfnOutput(this, 'AnalyticsNamedQueryIds', {
      description: 'Set as ANALYTICS_NAMED_QUERY_IDS on the analytics Lambda',
      value: Fn.join(',', ids),
    });
  }
}
