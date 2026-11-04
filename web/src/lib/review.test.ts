// #31: an IRL reviewer approves or corrects tags and summary; the record is marked reviewed.
// Corrections must keep the record valid under the #6 schema.
import { describe, expect, it } from 'vitest'
import { buildCompletedRecord, buildDeclinedRecord } from './record'
import { ReviewError, reviewRecord } from './review'

const MADE = new Date('2026-11-04T15:00:00Z')
const REVIEWED = new Date('2026-11-04T16:00:00Z')
const spanish = () => buildCompletedRecord({
  recordId: 'R-1', producerId: 'P-001', now: MADE, language: 'es', entityType: 'cooperative',
  summaryOriginal: 'La lluvia ha sido irregular.', summaryEnglish: 'Rainfall has been irregular.',
  tags: ['climate and weather'], insights: [], peerExamples: [], feedback: 'yes', piiFlag: false,
})

describe('reviewRecord', () => {
  it('approving marks the record reviewed, by whom and when, without changing content', () => {
    const r = reviewRecord(spanish(), {}, 'irl.reviewer', REVIEWED)
    expect(r.review_status).toBe('reviewed')
    expect(r.reviewed_by).toBe('irl.reviewer')
    expect(r.reviewed_at).toBe('2026-11-04T16:00:00.000Z')
    expect(r.tags).toEqual(['climate and weather'])
    expect(r.summary_original).toBe('La lluvia ha sido irregular.')
  })

  it('applies corrected tags and summaries', () => {
    const r = reviewRecord(spanish(), {
      tags: ['water', 'climate and weather'], summaryOriginal: 'La lluvia es irregular.', summaryEnglish: 'Rain is irregular.',
    }, 'irl.reviewer', REVIEWED)
    expect(r.tags).toEqual(['water', 'climate and weather'])
    expect(r.summary_original).toBe('La lluvia es irregular.')
    expect(r.summary_english).toBe('Rain is irregular.')
  })

  it('never changes who the record is about, its source or its consent', () => {
    const before = spanish()
    const r = reviewRecord(before, { tags: ['water'] }, 'irl.reviewer', REVIEWED)
    expect([r.producer_id, r.source, r.consent]).toEqual([before.producer_id, before.source, before.consent])
  })

  it('rejects removing every tag', () => {
    expect(() => reviewRecord(spanish(), { tags: [] }, 'irl.reviewer', REVIEWED)).toThrow(ReviewError)
  })

  it('rejects a tag outside the 11 challenge tags', () => {
    expect(() => reviewRecord(spanish(), { tags: ['drought'] }, 'irl.reviewer', REVIEWED)).toThrow(ReviewError)
  })

  it('rejects clearing the English summary of a non-English record', () => {
    expect(() => reviewRecord(spanish(), { summaryEnglish: '  ' }, 'irl.reviewer', REVIEWED)).toThrow(ReviewError)
  })

  it('rejects an empty summary in the producer’s words', () => {
    expect(() => reviewRecord(spanish(), { summaryOriginal: '' }, 'irl.reviewer', REVIEWED)).toThrow(ReviewError)
  })

  it('refuses to review a declined record: there is nothing to review', () => {
    const declined = buildDeclinedRecord({ recordId: 'R-2', producerId: 'P-001', now: MADE })
    expect(() => reviewRecord(declined, {}, 'irl.reviewer', REVIEWED)).toThrow(ReviewError)
  })

  it('requires a reviewer name', () => {
    expect(() => reviewRecord(spanish(), {}, ' ', REVIEWED)).toThrow(ReviewError)
  })
})
