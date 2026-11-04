import { describe, expect, it } from 'vitest'
import { liveProducers } from './liveProducers'

// The official demo scenarios (#35), read as raw text and parsed here, independently of the picker's JSON import
const raw = import.meta.glob<string>('../../../eval/scenarios/*.json', { eager: true, query: '?raw', import: 'default' })
const scenarios = Object.values(raw).map((text) => JSON.parse(text) as { id: string; producer_id: string; language: string; title: string })

describe('live producers (#124)', () => {
  it('offers exactly one card per official demo scenario, with its producer and language', () => {
    expect(scenarios.length).toBeGreaterThanOrEqual(6)
    expect(liveProducers.map((p) => p.scenarioId).sort()).toEqual(scenarios.map((s) => s.id).sort())
    for (const s of scenarios) {
      const card = liveProducers.find((p) => p.scenarioId === s.id)!
      expect(card).toMatchObject({ id: s.producer_id, language: s.language, title: s.title })
    }
  })

  it("lists the vision document's three required scenarios first", () => {
    expect(liveProducers.slice(0, 3).map((p) => p.scenarioId)).toEqual(['colombia-drought-es', 'mexico-price-drop-en', 'vietnam-labor-shortage-en'])
  })

  it('gives every card a flag', () => {
    for (const p of liveProducers) expect(p.flag).not.toBe('')
  })
})
