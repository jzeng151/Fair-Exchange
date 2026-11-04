// The demo's data numbers must match the pre-extracted regional fact table (#8) in data/.
// If you rebuild those tables, this fails until the demo's numbers are updated to match.
import { describe, expect, it } from 'vitest'
import facts from '../../../data/src/fx_data/regional_facts.json'
import sources from '../../../data/src/fx_data/regional_sources.json'
import { scenarios } from './scenarios'

type Fact = { text: string; source: string; metric: string }
type FactRegion = { country: string; region: string; facts: Fact[] }
type SourceRegion = { country: string; region: string; chirps: Record<string, { total_mm: number }> | null }

const factRegions = (facts as unknown as { regions: FactRegion[] }).regions
const coffeeFacts = (facts as unknown as { prices: Record<string, Fact[]> }).prices.coffee
const sourceRegions = (sources as unknown as { regions: SourceRegion[] }).regions
const arabica = (sources as unknown as { prices: { series: Record<string, { monthly: Record<string, number> }> } })
  .prices.series['Coffee, Arabica'].monthly

const scenario = (id: string) => scenarios.find((s) => s.id === id)!
const cauca = factRegions.find((r) => r.country === 'Colombia' && r.region === 'Cauca')!
const caucaYears = sourceRegions.find((r) => r.country === 'Colombia' && r.region === 'Cauca')!.chirps!
const mm = (year: number) => caucaYears[String(year)].total_mm
const baseline = Array.from({ length: 10 }, (_, i) => mm(2014 + i)).reduce((a, b) => a + b, 0) / 10
const factSources = new Set([
  ...factRegions.flatMap((r) => r.facts.map((f) => f.source)),
  ...coffeeFacts.map((f) => f.source),
])

describe('P-001 (Cauca rainfall and water stress) uses the real numbers', () => {
  const s = scenario('P-001')

  it('charts the real CHIRPS annual totals', () => {
    expect(s.chart.bars.map((b) => b.value)).toEqual([Math.round(baseline), Math.round(mm(2024)), Math.round(mm(2025))])
  })

  it('states the real rainfall change in English and Spanish', () => {
    const fact = cauca.facts.find((f) => f.metric === 'rainfall_change_pct')!
    const m = fact.text.match(/averaged ([\d,]+) mm a year in 2024-2025, ([\d.]+)% (below|above) the 2014-2023 average of ([\d,]+) mm/)!
    expect(m, fact.text).not.toBeNull()
    const [, recent, pct, , avg] = m
    expect(s.summary.en).toContain(`${pct}% below`)
    expect(s.summary.es).toContain(`${pct.replace('.', ',')}%`)
    const insight = s.insights[0].text
    expect(insight.en).toContain(recent)
    expect(insight.en).toContain(avg)
    expect(insight.en).toContain(`${pct}% below`)
    expect(insight.es).toContain(recent.replace(',', '.'))
    expect(insight.es).toContain(avg.replace(',', '.'))
  })

  it('states the real per-year change', () => {
    const pctVs = (year: number) => Math.round(Math.abs(mm(year) / baseline - 1) * 100)
    expect(s.insights[0].text.en).toContain(`2024 was about ${pctVs(2024)}% below`)
    expect(s.insights[0].text.en).toContain(`2025 about ${pctVs(2025)}% below`)
  })

  it('states the real Aqueduct band', () => {
    const fact = cauca.facts.find((f) => f.metric === 'baseline_water_stress')!
    const band = fact.text.match(/is ([^.]*)\.$/)![1]
    expect(band).toMatch(/^low to medium/)
    expect(s.insights[1].text.en).toContain(band)
    expect(s.insights[1].text.es).toContain('bajo a medio (10-20%)')
  })
})

describe('P-002 (arabica price) uses the real numbers', () => {
  const s = scenario('P-002')

  it('charts the real Pink Sheet prices', () => {
    const months = ['2025M10', '2026M01', '2026M04', '2026M07', '2026M10']
    expect(s.chart.bars.map((b) => b.value)).toEqual(months.map((k) => arabica[k]))
  })

  it('states the real price change and 5-year comparison', () => {
    const yoy = coffeeFacts[0].text.match(/averaged US\$ ([\d.]+) per kg in (\w+ \d{4}), ([\d.]+)% (lower|higher)/)!
    const fiveYear = coffeeFacts[1].text.match(/latest price is (\d+)% (below|above) that average/)!
    expect(yoy, coffeeFacts[0].text).not.toBeNull()
    expect(fiveYear, coffeeFacts[1].text).not.toBeNull()
    const [, price, month, pct, dir] = yoy
    const insight = s.insights[0].text.en!
    expect(insight).toContain(`US$${price} per kg in ${month}`)
    expect(insight).toContain(`${pct}% ${dir} than a year earlier`)
    expect(insight).toContain(`${fiveYear[1]}% ${fiveYear[2]} its 5-year average`)
    expect(s.summary.en).toContain(`${pct}% ${dir} in ${month}`)
  })

  it('says it is a world price, not a farm-gate price', () => {
    expect(s.insights[0].text.en).toContain('not a farm-gate price')
    expect(s.insights[0].strength).toBe('limited')
  })
})

describe('data sources', () => {
  it('name the real datasets, as the fact table does, not "synthetic extract"', () => {
    for (const [id, claim] of [['P-001', 0], ['P-001', 1], ['P-002', 0]] as const) {
      expect(factSources, `${id} insight ${claim}`).toContain(scenario(id).insights[claim].source)
    }
    expect(factSources).toContain(scenario('P-001').chart.source)
    expect(factSources).toContain(scenario('P-002').chart.source)
  })
})
