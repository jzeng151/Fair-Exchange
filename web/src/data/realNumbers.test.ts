// The demo's data numbers must match the pre-extracted regional fact table (#8) in data/.
// If you rebuild those tables, this fails until the demo's numbers are updated to match.
import { describe, expect, it } from 'vitest'
import factsCsv from '../../../data/src/fx_data/regional_facts.csv?raw'
import sources from '../../../data/src/fx_data/regional_sources.json'
import { scenarios } from './scenarios'

type Row = Record<string, string>
type SourceRegion = { country: string; region: string; chirps: Record<string, { total_mm: number }> | null }

/** RFC 4180 CSV: quoted fields may hold commas and doubled quotes. */
function parseCsv(text: string): Row[] {
  const records: string[][] = []
  let field = '', record: string[] = [], quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++ }
      else if (c === '"') quoted = false
      else field += c
    } else if (c === '"') quoted = true
    else if (c === ',') { record.push(field); field = '' }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      record.push(field); records.push(record); field = ''; record = []
    } else field += c
  }
  if (field || record.length) { record.push(field); records.push(record) }
  const [header, ...rows] = records
  return rows.map((r) => Object.fromEntries(header.map((h, i) => [h, r[i]])))
}

const rows = parseCsv(factsCsv)
const row = (where: Partial<Row>) => {
  const found = rows.find((r) => Object.entries(where).every(([k, v]) => r[k] === v))
  expect(found, JSON.stringify(where)).toBeDefined()
  return found!
}
const cauca = (indicator: string) => row({ scope: 'region', country: 'CO', admin1: 'Cauca', indicator })
const coffee = (indicator: string) => row({ scope: 'global', crop: 'coffee', indicator })

const sourceRegions = (sources as unknown as { regions: SourceRegion[] }).regions
const arabica = (sources as unknown as { prices: { series: Record<string, { monthly: Record<string, number> }> } })
  .prices.series['Coffee, Arabica'].monthly
const scenario = (id: string) => scenarios.find((s) => s.id === id)!
const caucaYears = sourceRegions.find((r) => r.country === 'Colombia' && r.region === 'Cauca')!.chirps!
const mm = (year: number) => caucaYears[String(year)].total_mm
const baseline = Array.from({ length: 10 }, (_, i) => mm(2014 + i)).reduce((a, b) => a + b, 0) / 10

describe('P-001 (Cauca rainfall and water stress) uses the real numbers', () => {
  const s = scenario('P-001')
  it('charts the real CHIRPS annual totals', () => {
    expect(s.chart.bars.map((b) => b.value)).toEqual([Math.round(baseline), Math.round(mm(2024)), Math.round(mm(2025))])
  })
  it('states the real rainfall change in English and Spanish', () => {
    const fact = cauca('rainfall_anomaly_pct')
    const m = fact.comparison.match(/vs 2014-2023 mean \(([\d,]+) mm vs ([\d,]+) mm a year\)/)!
    expect(m, fact.comparison).not.toBeNull()
    const [, recent, avg] = m
    const pct = String(Math.abs(Number(fact.value)))
    expect(Number(fact.value)).toBeLessThan(0)
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
    const band = cauca('water_stress_score').comparison.split(';')[0]
    expect(band).toMatch(/^low to medium/)
    expect(s.insights[1].text.en).toContain(band)
    expect(s.insights[1].text.es).toContain('bajo a medio (10-20%)')
    expect(cauca('water_stress_score_2050').comparison).toContain(`${band} by 2050`)
  })
})

describe('P-002 (arabica price) uses the real numbers', () => {
  const s = scenario('P-002')
  it('charts the real Pink Sheet prices', () => {
    const months = ['2025M10', '2026M01', '2026M04', '2026M07', '2026M10']
    expect(s.chart.bars.map((b) => b.value)).toEqual(months.map((k) => arabica[k]))
  })
  it('states the real price change and 5-year comparison', () => {
    const price = coffee('price_usd_per_kg')
    const fiveYear = coffee('price_vs_5yr_avg_pct')
    const yoy = price.comparison.match(/([\d.]+)% (lower|higher) than/)!
    expect(yoy, price.comparison).not.toBeNull()
    const [, pct, dir] = yoy
    const month = price.period
    const insight = s.insights[0].text.en!
    expect(insight).toContain(`US$${Number(price.value).toFixed(2)} per kg in ${month}`)
    expect(insight).toContain(`${pct}% ${dir} than a year earlier`)
    const v = Number(fiveYear.value)
    expect(insight).toContain(`${Math.round(Math.abs(v))}% ${v < 0 ? 'below' : 'above'} its 5-year average`)
    expect(s.summary.en).toContain(`${pct}% ${dir} in ${month}`)
  })
  it('says it is a world price, not a farm-gate price', () => {
    expect(s.insights[0].text.en).toContain('not a farm-gate price')
    expect(s.insights[0].strength).toBe('limited')
  })
})

describe('data sources', () => {
  // A source label ends in its fact ID in brackets (#8 spec) and starts with the dataset name.
  const cites = (source: string, fact: Row) =>
    source.startsWith(fact.source_name) && source.endsWith(`[${fact.fact_id}]`)
  it('cite the fact table rows the numbers come from', () => {
    const p1 = scenario('P-001'), p2 = scenario('P-002')
    expect(cites(p1.chart.source, cauca('rainfall_anomaly_pct')), p1.chart.source).toBe(true)
    expect(cites(p1.insights[0].source, cauca('rainfall_anomaly_pct')), p1.insights[0].source).toBe(true)
    expect(cites(p1.insights[1].source, cauca('water_stress_score_2050')), p1.insights[1].source).toBe(true)
    expect(cites(p2.chart.source, coffee('price_usd_per_kg')), p2.chart.source).toBe(true)
    expect(cites(p2.insights[0].source, coffee('price_usd_per_kg')), p2.insights[0].source).toBe(true)
  })
})
