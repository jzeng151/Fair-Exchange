// Builds the record the chat hands to the backend, typed by the GENERATED #6 schema types.
// (The Pydantic models in agent/ are the source of truth; never hand-edit the generated types.)
import type { Claim, CompletedRecord, DeclinedRecord } from '../../../api/src/types/conversation-record'

export interface CompletedInput {
  recordId: string
  producerId: string // from the session, never from what the producer types
  now: Date
  language: string // ISO 639-1, e.g. 'es'
  entityType: string
  summaryOriginal: string
  summaryEnglish: string
  tags: CompletedRecord['tags'] // at least one of the 11 challenge tags (schema rule)
  insights: Claim[]
  peerExamples: Claim[]
  feedback: CompletedRecord['feedback']
  piiFlag: boolean
}

export function buildCompletedRecord(input: CompletedInput): CompletedRecord {
  const at = input.now.toISOString()
  return {
    record_id: input.recordId,
    producer_id: input.producerId,
    status: 'completed',
    created_at: at,
    updated_at: at,
    version: 1,
    consent: { scope: 'internal', recorded_at: at },
    consent_history: [{ scope: 'internal', recorded_at: at }],
    source: 'agent conversation',
    language: input.language,
    entity_type: input.entityType,
    summary_original: input.summaryOriginal,
    // The schema requires an English version only for non-English conversations
    summary_english: input.language === 'en' ? null : input.summaryEnglish,
    tags: input.tags,
    // limited when the producer was shown no insights or no peer examples (#26)
    evidence: input.insights.length && input.peerExamples.length ? 'full' : 'limited',
    insights: input.insights,
    peer_examples: input.peerExamples,
    feedback: input.feedback,
    pii_flag: input.piiFlag,
    review_status: 'pending',
    reviewed_by: null,
    reviewed_at: null,
  }
}

export function buildDeclinedRecord(input: { recordId: string; producerId: string; now: Date }): DeclinedRecord {
  const at = input.now.toISOString()
  // A decline keeps identifiers, status and time only: no narrative content
  return {
    record_id: input.recordId,
    producer_id: input.producerId,
    status: 'declined',
    created_at: at,
    updated_at: at,
    version: 1,
    consent: { scope: 'declined', recorded_at: at },
    consent_history: [{ scope: 'declined', recorded_at: at }],
    source: 'agent conversation',
  }
}
