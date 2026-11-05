// Live mode (#116, #124): the producers the live chat can act as, one card per official demo scenario.
// Built from the scenario files themselves (eval/scenarios/S1..S7.json, #35), so the picker can never drift
// from them: same producer, same language, same title. S5 and S7 share a producer, so cards are keyed by
// scenario. The presenter follows the scenario's turns (see eval/scenarios/README.md). Local only: choosing
// a producer here stands in for sign-in (#11).
export interface LiveProducer {
  id: string // the producer ID the scenario uses (#7's synthetic producers)
  scenarioId: string
  title: string
  language: string
  flag: string
}

interface ScenarioFile { scenario_id: string; producer_id: string; language: string; title: string }

const files = import.meta.glob<ScenarioFile>('../../../eval/scenarios/S*.json', { eager: true, import: 'default' })

// The vision document's three required scenarios first (S1–S3), then the decline, PII, out-of-scope and
// contrast paths (S4–S7).
const ORDER = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
const FLAGS: Record<string, string> = { S1: '🇨🇴', S2: '🇲🇽', S3: '🇻🇳', S4: '🇭🇳', S5: '🇨🇮', S6: '🇨🇮', S7: '🇨🇮' }
const rank = (id: string) => (ORDER.includes(id) ? ORDER.indexOf(id) : ORDER.length)

export const liveProducers: LiveProducer[] = Object.values(files)
  .map((s) => ({ id: s.producer_id, scenarioId: s.scenario_id, title: s.title, language: s.language, flag: FLAGS[s.scenario_id] ?? '🌱' }))
  .sort((a, b) => rank(a.scenarioId) - rank(b.scenarioId) || a.scenarioId.localeCompare(b.scenarioId))

export const languageName: Record<string, string> = { en: 'English', es: 'Español', fr: 'Français' }
