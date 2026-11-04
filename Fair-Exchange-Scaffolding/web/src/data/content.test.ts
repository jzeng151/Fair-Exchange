// #30: the demo's scripted content must be honest and complete.
import { describe, expect, it } from 'vitest'
import clauses from '../../../../data/src/fx_data/clauses.json'
import { t } from './i18n'
import { scenarios } from './scenarios'

const realClauses = new Set((clauses as { id: string }[]).map((c) => c.id))
const DIRECTIVE = /\b(you should|we recommend|the best option|you must|debería|deberían|recomendamos|le recomiendo|la mejor opción|tiene que)\b/i

function allStrings(value: unknown): string[] {
  if (typeof value === 'string') return [value]
  if (typeof value === 'function') return []
  if (Array.isArray(value)) return value.flatMap(allStrings)
  if (value && typeof value === 'object') return Object.values(value).flatMap(allStrings)
  return []
}

function shape(value: unknown): unknown {
  if (typeof value === 'function') return 'function'
  if (Array.isArray(value)) return value.map(shape)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shape(v)]))
  return typeof value
}

describe('scenarios', () => {
  it('cite only clauses that exist in the APS/FPS standards (#9)', () => {
    const cited = scenarios.flatMap((s) => [...s.insights, ...s.peers].map((c) => c.clause))
    expect(cited.length).toBeGreaterThan(0)
    expect(cited.filter((c) => !realClauses.has(c))).toEqual([])
  })

  it('give every Spanish line an English version (subtitles)', () => {
    const spanish = scenarios.filter((s) => s.language === 'es')
    expect(spanish.length).toBeGreaterThan(0)
    for (const s of spanish) {
      const bilingual = [s.summary, ...s.insights.map((i) => i.text), ...s.peers.map((p) => p.text),
        ...s.peers.flatMap((p) => (p.tradeoff ? [p.tradeoff] : [])), ...Object.values(s.chips).flat()]
      expect(bilingual.filter((b) => !b.es || !b.en)).toEqual([])
    }
  })

  it('cover English and at least one other language', () => {
    expect(new Set(scenarios.map((s) => s.language))).toEqual(new Set(['en', 'es']))
  })
})

describe('wording', () => {
  it('never tells the producer what to do', () => {
    const texts = [...allStrings(t), ...allStrings(scenarios)]
    expect(texts.filter((x) => DIRECTIVE.test(x))).toEqual([])
  })

  it('has the same Spanish and English copy keys', () => {
    expect(shape(t.es)).toEqual(shape(t.en))
  })
})
