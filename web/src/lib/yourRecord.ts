// "Your record" view logic (#32), kept pure so it can be tested without the DOM. In demo mode the
// records come from this browser (demoStore); when GET /me/records (#32) lands, the view swaps the
// source and these same functions shape what the producer sees.
import type { ConversationRecord } from '../../../api/src/types/conversation-record'
import { tagNames, type Lang } from '../data/i18n'

/** What the producer may see for one listed record. Mirrors the GET /me/records projection (#32). */
export interface YourRecordRow {
  recordId: string
  closedAt: string
  status: 'completed' | 'declined'
  // Completed only:
  language?: string
  consentScope?: 'internal' | 'internal_and_outward'
  consentAt?: string
  summary?: string
  changedByReviewer?: boolean
  tags?: string[]
  insights?: { text: string; source: string; clause: string }[]
  peerExamples?: { text: string; source: string; clause: string }[]
  feedback?: 'yes' | 'somewhat' | 'no' | null
  reviewStatus?: 'pending' | 'reviewed'
}

/** A closed record whose outcome is decided (completed with a stored consent scope, or declined). */
function isDecided(r: ConversationRecord): boolean {
  if (typeof r.closed_at !== 'string') return false
  if (r.status === 'declined') return true
  const scope = r.consent?.scope
  return r.status === 'completed' && (scope === 'internal' || scope === 'internal_and_outward')
}

function claim(c: { text: string; citation: { source: string; standard_clause: string } }) {
  return { text: c.text, source: c.citation.source, clause: c.citation.standard_clause }
}

/** Projects one record to what the producer may see. Never exposes summary_english, pii_*, reviewer id. */
export function toRow(r: ConversationRecord): YourRecordRow {
  if (r.status === 'declined') {
    return { recordId: r.record_id, closedAt: r.closed_at as string, status: 'declined' }
  }
  const summary = r.reviewer_summary_original ?? r.summary_original
  const tags = (r.reviewer_tags ?? r.tags) as string[]
  const changed = r.reviewer_summary_original != null || r.reviewer_tags != null
  return {
    recordId: r.record_id,
    closedAt: r.closed_at as string,
    status: 'completed',
    language: r.language,
    consentScope: r.consent.scope,
    consentAt: r.consent.recorded_at,
    summary,
    changedByReviewer: changed,
    tags,
    insights: (r.insights ?? []).map(claim),
    peerExamples: (r.peer_examples ?? []).map(claim),
    feedback: r.feedback ?? null,
    reviewStatus: r.review_status ?? 'pending',
  }
}

/**
 * The producer's own decided, closed records, newest first, projected for display. A producer sees
 * only their own records; the producer ID is the caller's, never chosen in the view.
 */
export function yourRecords(all: ConversationRecord[], producerId: string): YourRecordRow[] {
  return all
    .filter((r) => r.producer_id === producerId && isDecided(r))
    .sort((a, b) => String(b.closed_at).localeCompare(String(a.closed_at)))
    .map(toRow)
}

/** A tag's name in the producer's language, falling back to the raw tag if it has no translation. */
export function tagName(tag: string, lang: Lang): string {
  return tagNames[lang]?.[tag] ?? tag
}
