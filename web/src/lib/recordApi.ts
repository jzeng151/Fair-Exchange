import type { CompletedRecord, ConversationRecord } from '../../../api/src/types/conversation-record'
import type { YourRecordRow } from './yourRecord'

export class RecordApiError extends Error {
  constructor(readonly status: number) {
    super(status === 409 ? 'This record changed. Reload to see the latest.'
      : status === 401 ? 'The passcode was not accepted.'
        : status === 403 ? 'This sign-in does not have access to this view.'
          : status === 0 ? 'Cannot reach the service. Check your connection and retry.' : `Request failed (${status}). Please retry.`)
  }
}
export type ReviewSummary = Pick<CompletedRecord, 'record_id' | 'closed_at' | 'language' | 'entity_type' | 'tags' | 'review_status' | 'pii_flag' | 'pii_review' | 'evidence' | 'version'>
type ProducerRecord = Pick<CompletedRecord, 'record_id' | 'closed_at' | 'language' | 'consent' | 'tags' | 'insights' | 'peer_examples' | 'earlier_answers' | 'feedback' | 'review_status'> & {
  status: ConversationRecord['status']; summary?: string; changed_by_reviewer?: boolean
}
export function recordApi(base: string, headers: Record<string, string>, doFetch: typeof fetch = (...args) => fetch(...args)) {
  async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    let response: Response
    try {
      response = await doFetch(`${base.replace(/\/+$/, '')}${path}`, {
        method, headers: { ...headers, ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      })
    } catch { throw new RecordApiError(0) }
    if (!response.ok) throw new RecordApiError(response.status)
    return response.json() as Promise<T>
  }
  return {
    identity: () => request<{ user_id: string; roles: string[] }>('/me'),
    list: (query = '') => request<{ records: ReviewSummary[] }>(`/records${query}`),
    get: (id: string) => request<CompletedRecord>(`/records/${encodeURIComponent(id)}`),
    patch: (id: string, body: unknown) => request<CompletedRecord>(`/records/${encodeURIComponent(id)}`, 'PATCH', body),
    approve: (id: string, version: number) => request<CompletedRecord>(`/records/${encodeURIComponent(id)}/approve`, 'POST', { version }),
    mine: async (): Promise<YourRecordRow[]> => {
      const { records } = await request<{ records: ProducerRecord[] }>('/me/records')
      const claim = (c: NonNullable<CompletedRecord['insights']>[number]) => ({ text: c.text, source: c.citation.source, clause: c.citation.standard_clause })
      return records.map((r) => r.status === 'declined'
        ? { recordId: r.record_id, closedAt: r.closed_at!, status: 'declined' }
        : { recordId: r.record_id, closedAt: r.closed_at!, status: 'completed', language: r.language,
          consentScope: r.consent.scope, consentAt: r.consent.recorded_at, summary: r.summary,
          changedByReviewer: r.changed_by_reviewer, tags: r.tags, insights: r.insights?.map(claim),
          peerExamples: r.peer_examples?.map(claim), feedback: r.feedback, reviewStatus: r.review_status })
    },
  }
}
