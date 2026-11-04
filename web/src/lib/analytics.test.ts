// #33 (dashboard) follows the #29 analytics rules:
//   consented records only; declines appear as counts only; any breakdown with n < 5 is hidden;
//   reviewed records are shown by default.
import { describe, expect, it } from 'vitest'
import type { ConversationRecord } from '../../../api/src/types/conversation-record'
import { buildCompletedRecord, buildDeclinedRecord } from './record'
import { MIN_GROUP, summarize } from './analytics'

const NOW = new Date('2026-11-04T12:00:00Z')
let n = 0
function rec(o: { lang?: string; entity?: string; tags?: string[]; feedback?: 'yes' | 'somewhat' | 'no' | null; reviewed?: boolean } = {}): ConversationRecord {
  const r = buildCompletedRecord({
    recordId: `R-${++n}`, producerId: `P-SECRET-${n}`, now: NOW, language: o.lang ?? 'es', entityType: o.entity ?? 'cooperative',
    summaryOriginal: `secret summary ${n}`, summaryEnglish: `secret english ${n}`, tags: (o.tags ?? ['water']) as never,
    insights: [], peerExamples: [], feedback: o.feedback === undefined ? 'yes' : o.feedback, piiFlag: false,
  })
  return o.reviewed === false ? r : { ...r, review_status: 'reviewed', reviewed_by: 'irl', reviewed_at: NOW.toISOString() }
}
const many = (k: number, o: Parameters<typeof rec>[0] = {}) => Array.from({ length: k }, () => rec(o))
const declined = (k: number) => Array.from({ length: k }, () => buildDeclinedRecord({ recordId: `D-${++n}`, producerId: `P-SECRET-${n}`, now: NOW }))
const bucket = (b: { buckets: { key: string; count: number | null }[] }, key: string) => b.buckets.find((x) => x.key === key)?.count

describe('summarize (analytics rules)', () => {
  it('hides groups smaller than 5', () => {
    expect(MIN_GROUP).toBe(5)
    const s = summarize([...many(6, { lang: 'es' }), ...many(4, { lang: 'en' })])
    expect(bucket(s.byLanguage, 'es')).toBeNull() // hidden too, or 'en' could be worked out from the total
    expect(bucket(s.byLanguage, 'en')).toBeNull()
    const t = summarize([...many(6, { lang: 'es' }), ...many(5, { lang: 'en' })])
    expect(bucket(t.byLanguage, 'es')).toBe(6)
    expect(bucket(t.byLanguage, 'en')).toBe(5)
  })

  it('hides one more group when a single hidden group could be worked out from the total', () => {
    const s = summarize([...many(9, { entity: 'cooperative' }), ...many(6, { entity: 'estate' }), ...many(2, { entity: 'smallholder' })])
    expect(s.included).toBe(17)
    expect(bucket(s.byEntity, 'smallholder')).toBeNull()
    expect(bucket(s.byEntity, 'estate')).toBeNull() // smallest visible group, hidden as a complement
    expect(bucket(s.byEntity, 'cooperative')).toBe(9)
  })

  it('never puts record-level details in the output', () => {
    const out = JSON.stringify(summarize([...many(12), ...declined(6)]))
    expect(out).not.toMatch(/P-SECRET|secret summary|secret english|R-\d|D-\d/)
  })

  it('counts declines, but never puts them in breakdowns', () => {
    const s = summarize([...many(5, { tags: ['water'] }), ...declined(7)])
    expect(s.declined).toBe(7)
    expect(s.included).toBe(5)
    expect(bucket(s.byTag, 'water')).toBe(5)
  })

  it('hides a decline count below 5', () => {
    expect(summarize([...many(5), ...declined(3)]).declined).toBeNull()
  })

  it('shows reviewed records by default and pending ones only on request', () => {
    const records = [...many(5, { lang: 'es' }), ...many(5, { lang: 'en', reviewed: false })]
    const reviewedOnly = summarize(records)
    expect(reviewedOnly.included).toBe(5)
    expect(reviewedOnly.pendingNotShown).toBe(5)
    expect(bucket(reviewedOnly.byLanguage, 'en')).toBeUndefined()
    const all = summarize(records, { includePending: true })
    expect(all.included).toBe(10)
    expect(bucket(all.byLanguage, 'en')).toBe(5)
  })

  it('hides everything when fewer than 5 records are included', () => {
    const s = summarize(many(4))
    expect(s.included).toBeNull()
    expect(s.byTag.buckets.every((b) => b.count === null)).toBe(true)
  })

  it('counts a record once per tag; buckets are sorted largest first, hidden last', () => {
    const s = summarize([...many(5, { tags: ['water', 'climate and weather'] }), ...many(3, { tags: ['water'] }), ...many(2, { tags: ['health'] })])
    expect(s.byTag.buckets.map((b) => [b.key, b.count])).toEqual([['water', 8], ['climate and weather', 5], ['health', null]])
  })

  it('reports feedback with "no answer" as its own group', () => {
    const s = summarize([...many(5, { feedback: 'yes' }), ...many(5, { feedback: null })])
    expect(bucket(s.byFeedback, 'yes')).toBe(5)
    expect(bucket(s.byFeedback, 'no answer')).toBe(5)
  })
})
