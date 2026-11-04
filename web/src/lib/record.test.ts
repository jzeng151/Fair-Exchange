// #30: what the chat hands to the backend must match the #6 record schema.
import { describe, expect, it } from 'vitest'
import type { CompletedRecord } from '../../../api/src/types/conversation-record'
import { buildCompletedRecord, buildDeclinedRecord } from './record'

const NOW = new Date('2026-11-04T15:30:00Z')
const claim = (text: string, clause: string) => ({
  text, citation: { source: 'CHIRPS rainfall (demo extract)', standard_clause: clause, strength: 'exact' as const },
})

describe('buildCompletedRecord', () => {
  const base = {
    recordId: 'R-1', producerId: 'P-001', now: NOW, language: 'es', entityType: 'cooperative',
    summaryOriginal: 'La lluvia ha sido irregular.', summaryEnglish: 'Rainfall has been irregular.',
    tags: ['climate and weather', 'water'] as CompletedRecord['tags'], insights: [claim('Rainfall was 22% below average.', 'APS 4.1.1')],
    peerExamples: [claim('A cooperative funded rainwater catchment.', 'APS 4.1.1')], feedback: null, piiFlag: false,
  }

  it('marks the record as an agent conversation, pending review, stored internally', () => {
    const r = buildCompletedRecord(base)
    expect(r.source).toBe('agent conversation')
    expect(r.status).toBe('completed')
    expect(r.review_status).toBe('pending')
    expect(r.consent).toEqual({ scope: 'internal', recorded_at: '2026-11-04T15:30:00.000Z' })
  })

  it('keeps the producer’s words and the English version for a Spanish conversation', () => {
    const r = buildCompletedRecord(base)
    expect(r.summary_original).toBe('La lluvia ha sido irregular.')
    expect(r.summary_english).toBe('Rainfall has been irregular.')
  })

  it('keeps every claim with its standard clause', () => {
    const r = buildCompletedRecord(base)
    expect(r.insights?.[0]?.citation.standard_clause).toBe('APS 4.1.1')
    expect(r.peer_examples).toHaveLength(1)
  })

  it('stores no separate English summary for an English conversation', () => {
    const r = buildCompletedRecord({ ...base, language: 'en', summaryOriginal: 'Rain is irregular.', summaryEnglish: 'ignored' })
    expect(r.summary_english).toBeNull()
  })
})

describe('buildDeclinedRecord', () => {
  it('holds only identifiers, status, time and declined consent: no narrative', () => {
    const r = buildDeclinedRecord({ recordId: 'R-2', producerId: 'P-001', now: NOW })
    expect(Object.keys(r).sort()).toEqual(['consent', 'created_at', 'producer_id', 'record_id', 'source', 'status'])
    expect(r.consent.scope).toBe('declined')
    expect(r.status).toBe('declined')
  })
})
