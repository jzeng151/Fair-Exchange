import { describe, expect, it } from 'vitest'
import type { ConversationRecord } from '../../../api/src/types/conversation-record'
import { tagName, yourRecords } from './yourRecord'

const completed = (over: Record<string, unknown> = {}): ConversationRecord =>
  ({
    record_id: 'r1',
    producer_id: 'P-001',
    created_at: '2026-11-04T10:00:00Z',
    updated_at: '2026-11-04T10:30:00Z',
    version: 3,
    status: 'completed',
    closed_at: '2026-11-04T10:30:00Z',
    consent: { scope: 'internal', recorded_at: '2026-11-04T10:20:00Z' },
    language: 'es',
    entity_type: 'cooperative',
    summary_original: 'La lluvia bajó',
    tags: ['water'],
    evidence: 'full',
    insights: [{ text: 'Rain fell', citation: { source: 'CHIRPS', standard_clause: 'APS 1.1' } }],
    peer_examples: [],
    feedback: 'yes',
    review_status: 'pending',
    reviewer_tags: null,
    reviewer_summary_original: null,
    ...over,
  }) as ConversationRecord

const declined = (over: Record<string, unknown> = {}): ConversationRecord =>
  ({
    record_id: 'd1',
    producer_id: 'P-001',
    created_at: '2026-11-04T11:00:00Z',
    updated_at: '2026-11-04T11:10:00Z',
    version: 1,
    status: 'declined',
    closed_at: '2026-11-04T11:10:00Z',
    consent: { scope: 'declined', recorded_at: '2026-11-04T11:05:00Z' },
    ...over,
  }) as ConversationRecord

describe('yourRecords', () => {
  it('shows only the producer’s own records', () => {
    const rows = yourRecords([completed(), completed({ record_id: 'x', producer_id: 'P-002' })], 'P-001')
    expect(rows.map((r) => r.recordId)).toEqual(['r1'])
  })

  it('excludes open conversations (no closed_at)', () => {
    const rows = yourRecords([completed(), completed({ record_id: 'open', closed_at: null })], 'P-001')
    expect(rows.map((r) => r.recordId)).toEqual(['r1'])
  })

  it('excludes records whose outcome is not decided', () => {
    const undecided = completed({ record_id: 'u', consent: { scope: '', recorded_at: '2026-11-04T10:20:00Z' } })
    expect(yourRecords([undecided], 'P-001')).toEqual([])
  })

  it('shows a declined record as only id, closed time and declined', () => {
    expect(yourRecords([declined()], 'P-001')).toEqual([
      { recordId: 'd1', closedAt: '2026-11-04T11:10:00Z', status: 'declined' },
    ])
  })

  it('orders newest first', () => {
    const rows = yourRecords(
      [
        completed({ record_id: 'a', closed_at: '2026-11-01T10:00:00Z' }),
        completed({ record_id: 'b', closed_at: '2026-11-03T10:00:00Z' }),
        completed({ record_id: 'c', closed_at: '2026-11-02T10:00:00Z' }),
      ],
      'P-001',
    )
    expect(rows.map((r) => r.recordId)).toEqual(['b', 'c', 'a'])
  })

  it('uses the effective (reviewer-or-agent) summary and tags and flags a reviewer change', () => {
    const rows = yourRecords(
      [completed({ reviewer_summary_original: 'Corregido', reviewer_tags: ['soil and land'] })],
      'P-001',
    )
    expect(rows[0]!.summary).toBe('Corregido')
    expect(rows[0]!.tags).toEqual(['soil and land'])
    expect(rows[0]!.changedByReviewer).toBe(true)
  })

  it('never exposes summary_english, pii_*, or the reviewer identity', () => {
    const rows = yourRecords(
      [completed({ summary_english: 'Rain fell', pii_flag: true, pii_review: 'confirmed', reviewed_by: 'rev-1' })],
      'P-001',
    )
    const row = rows[0]! as unknown as Record<string, unknown>
    for (const forbidden of ['summary_english', 'pii_flag', 'pii_review', 'reviewed_by']) {
      expect(row).not.toHaveProperty(forbidden)
    }
  })
})

describe('tagName', () => {
  it('translates known tags per language', () => {
    expect(tagName('water', 'es')).toBe('Agua')
    expect(tagName('water', 'en')).toBe('Water')
  })

  it('falls back to the raw tag when there is no translation', () => {
    expect(tagName('unknown-tag', 'es')).toBe('unknown-tag')
  })
})
