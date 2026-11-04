// #31: the "Load demo records" button must only ever produce valid records.
import { describe, expect, it } from 'vitest'
import clauses from '../../../data/src/fx_data/clauses.json'
import { demoRecords } from './demoSeed'
import { reviewRecord } from './review'

const realClauses = new Set((clauses as { id: string }[]).map((c) => c.id))
const NOW = new Date('2026-11-04T12:00:00Z')

describe('demoRecords', () => {
  const { records } = demoRecords(NOW)

  it('include a pending record, a personal-info flag and a decline, so every review state can be shown', () => {
    expect(records.some((r) => r.status === 'completed' && r.review_status === 'pending')).toBe(true)
    expect(records.some((r) => r.status === 'completed' && r.pii_flag)).toBe(true)
    expect(records.some((r) => r.status === 'declined')).toBe(true)
  })

  it('are all reviewable as they are (valid tags and summaries)', () => {
    for (const r of records.filter((x) => x.status === 'completed')) {
      expect(() => reviewRecord(r, {}, 'check', NOW)).not.toThrow()
    }
  })

  it('cite only real APS/FPS clauses', () => {
    const cited = records.flatMap((r) => (r.status === 'completed' ? [...(r.insights ?? []), ...(r.peer_examples ?? [])] : []))
      .map((c) => c.citation.standard_clause)
    expect(cited.length).toBeGreaterThan(0)
    expect(cited.filter((c) => !realClauses.has(c))).toEqual([])
  })

  it('come with a reasoning trace for every completed record', () => {
    const { traces } = demoRecords(NOW)
    for (const r of records.filter((x) => x.status === 'completed')) expect(traces[r.record_id]?.length).toBeGreaterThan(0)
  })
})
