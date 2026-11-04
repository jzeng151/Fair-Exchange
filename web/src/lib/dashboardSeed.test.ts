// #33: "Load sample data" must give the dashboard meaningful breakdowns, using only valid records.
import { describe, expect, it } from 'vitest'
import { summarize } from './analytics'
import { dashboardRecords } from './dashboardSeed'
import { reviewRecord } from './review'

const NOW = new Date('2026-11-04T12:00:00Z')

describe('dashboardRecords', () => {
  const records = dashboardRecords(NOW)

  it('is the same every time (so the demo is repeatable)', () => {
    expect(JSON.stringify(dashboardRecords(NOW))).toBe(JSON.stringify(records))
  })

  it('has unique, clearly synthetic IDs', () => {
    const ids = records.map((r) => r.record_id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.every((id) => id.startsWith('SEED-'))).toBe(true)
  })

  it('contains reviewed, pending and declined records', () => {
    expect(records.some((r) => r.status === 'declined')).toBe(true)
    expect(records.some((r) => r.status === 'completed' && r.review_status === 'pending')).toBe(true)
    expect(records.some((r) => r.status === 'completed' && r.review_status === 'reviewed')).toBe(true)
  })

  it('every completed record is valid under the review rules', () => {
    for (const r of records) if (r.status === 'completed') expect(() => reviewRecord(r, {}, 'check', NOW)).not.toThrow()
  })

  it('gives meaningful breakdowns by default, with at least one small group hidden', () => {
    const s = summarize(records)
    expect(s.included).toBeGreaterThanOrEqual(30)
    expect(s.declined).not.toBeNull()
    for (const b of [s.byTag, s.byLanguage, s.byEntity, s.byFeedback]) {
      expect(b.buckets.filter((x) => x.count !== null).length).toBeGreaterThanOrEqual(2)
    }
    expect(s.byTag.buckets.some((x) => x.count === null)).toBe(true) // shows the n < 5 rule working
  })
})
