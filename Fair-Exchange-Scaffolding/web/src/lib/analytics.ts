// Aggregate breakdowns for the admin dashboard (issue #33), following the analytics API rules (#29):
//   - consented records only; declines appear as a count only
//   - any group with fewer than MIN_GROUP records is hidden
//   - reviewed records are shown by default; pending ones only on request
// The output is aggregate counts only: no IDs, summaries or other record-level fields.
// `AnalyticsSummary` is the response shape the dashboard expects from #29.
import type { CompletedRecord, ConversationRecord } from '../../../../api/src/types/conversation-record'

export const MIN_GROUP = 5

/** count is null when the group is hidden (fewer than MIN_GROUP, or hidden to protect another hidden group). */
export interface Bucket { key: string; count: number | null }
export interface Breakdown { buckets: Bucket[] }

export interface AnalyticsSummary {
  includePending: boolean
  /** consented records in this view */
  included: number | null
  /** pending records left out of a reviewed-only view */
  pendingNotShown: number | null
  declined: number | null
  byTag: Breakdown
  byLanguage: Breakdown
  byEntity: Breakdown
  byFeedback: Breakdown
}

/** 1–4 is hidden; 0 says nothing about anyone and is shown. */
const small = (k: number) => k > 0 && k < MIN_GROUP
const shown = (k: number): number | null => (small(k) ? null : k)

function countBy(keysPerRecord: string[][]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const keys of keysPerRecord) for (const k of new Set(keys)) counts.set(k, (counts.get(k) ?? 0) + 1)
  return counts
}

/**
 * @param exclusive true when every record falls in exactly one group, so the groups add up to the
 *   total. Then a single hidden group could be worked out by subtraction, and the smallest visible
 *   group is hidden as well.
 */
function breakdown(counts: Map<string, number>, exclusive: boolean, totalHidden: boolean): Breakdown {
  const entries = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  const hidden = new Set(entries.filter(([, k]) => totalHidden || small(k)).map(([key]) => key))
  if (exclusive && hidden.size === 1) {
    const smallestVisible = entries.filter(([key]) => !hidden.has(key)).at(-1)
    if (smallestVisible) hidden.add(smallestVisible[0])
  }
  const buckets = entries.map(([key, k]) => ({ key, count: hidden.has(key) ? null : k }))
  return { buckets: [...buckets.filter((b) => b.count !== null), ...buckets.filter((b) => b.count === null)] }
}

export function summarize(records: ConversationRecord[], opts: { includePending?: boolean } = {}): AnalyticsSummary {
  const includePending = opts.includePending ?? false
  const completed = records.filter((r): r is CompletedRecord => r.status === 'completed')
  const inView = completed.filter((r) => includePending || r.review_status === 'reviewed')
  const totalHidden = inView.length < MIN_GROUP

  return {
    includePending,
    included: totalHidden ? null : inView.length,
    pendingNotShown: includePending ? 0 : shown(completed.length - inView.length),
    declined: shown(records.length - completed.length),
    byTag: breakdown(countBy(inView.map((r) => r.tags)), false, totalHidden),
    byLanguage: breakdown(countBy(inView.map((r) => [r.language])), true, totalHidden),
    byEntity: breakdown(countBy(inView.map((r) => [r.entity_type])), true, totalHidden),
    byFeedback: breakdown(countBy(inView.map((r) => [r.feedback ?? 'no answer'])), true, totalHidden),
  }
}
