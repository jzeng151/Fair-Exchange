// Live analytics (#29, #33): the admin dashboard's client for `GET /analytics` on the deployed API.
// The API has already hidden small groups (suppression happens on the server, #29); this only maps its
// response to the dashboard's breakdowns and never computes totals, so nothing hidden can be recovered here.
import type { Breakdown } from './analytics'
import { LiveError } from './liveClient'

/** A hidden cell is `{suppressed: true}`, never a number (api/src/analytics/suppression.ts). */
export type Cell = number | { suppressed: true }

export interface AnalyticsSection {
  completed: Cell
  declined: Cell
  by_tag: Record<string, Cell>
  by_language: Record<string, Cell>
  by_entity_type: Record<string, Cell>
  by_consent_scope: Record<string, Cell>
  by_feedback: Record<string, Cell>
  by_evidence: Record<string, Cell>
  ai_footprint: { model_id: string; input_tokens: number; output_tokens: number }[]
}

export interface AnalyticsResponse {
  filters: { include_pending: boolean }
  live: AnalyticsSection
  seeded: AnalyticsSection
}

/** The admin sign-in stand-in (docs/specs/11-identity.md): the admin passcode alone grants the admin role. */
export const ADMIN_PASSCODE_HEADER = 'x-demo-admin-passcode'

export const cellCount = (c: Cell | undefined): number | null => (typeof c === 'number' ? c : null)

/** Shown groups largest first, then hidden ones, as the demo dashboard orders them. */
export function toBreakdown(cells: Record<string, Cell>): Breakdown {
  const buckets = Object.entries(cells).map(([key, c]) => ({ key, count: cellCount(c) }))
  const shown = buckets.filter((b) => b.count !== null).sort((a, b) => b.count! - a.count! || a.key.localeCompare(b.key))
  const hidden = buckets.filter((b) => b.count === null).sort((a, b) => a.key.localeCompare(b.key))
  return { buckets: [...shown, ...hidden] }
}

export async function fetchAnalytics(
  baseUrl: string,
  passcode: string,
  includePending: boolean,
  doFetch: typeof fetch = (...a) => fetch(...a),
): Promise<AnalyticsResponse> {
  const url = `${baseUrl.replace(/\/+$/, '')}/analytics?include_pending=${includePending ? 'true' : 'false'}`
  let res: Response
  try {
    res = await doFetch(url, { headers: { [ADMIN_PASSCODE_HEADER]: passcode } })
  } catch {
    throw new LiveError(0, `Can't reach the analytics API at ${baseUrl}`)
  }
  if (!res.ok) throw new LiveError(res.status, `Request failed (${res.status})`)
  return (await res.json()) as AnalyticsResponse
}
