// Live mode (#116, #124): the producers the live chat can act as, one card per official demo scenario.
// Built from the scenario files themselves (eval/scenarios/*.json, #35), so the picker can never drift from
// them: same sample producer, same language, same title. The presenter follows the scenario's turns
// (see eval/scenarios/README.md). Local only: choosing a producer here stands in for sign-in (#11).
export interface LiveProducer {
  id: string // the sample producer ID the scenario uses
  scenarioId: string
  title: string
  language: string
  flag: string
}

interface ScenarioFile { id: string; producer_id: string; language: string; title: string }

const files = import.meta.glob<ScenarioFile>('../../../eval/scenarios/*.json', { eager: true, import: 'default' })

// The vision document's three required scenarios first, then the decline, PII and French paths.
const ORDER = ['colombia-drought-es', 'mexico-price-drop-en', 'vietnam-labor-shortage-en', 'honduras-decline-es', 'peru-water-pii-es', 'cote-divoire-cocoa-pii-fr']
const FLAGS: Record<string, string> = { colombia: '🇨🇴', mexico: '🇲🇽', vietnam: '🇻🇳', honduras: '🇭🇳', peru: '🇵🇪', cote: '🇨🇮' }
const rank = (id: string) => (ORDER.includes(id) ? ORDER.indexOf(id) : ORDER.length)

export const liveProducers: LiveProducer[] = Object.values(files)
  .map((s) => ({ id: s.producer_id, scenarioId: s.id, title: s.title, language: s.language, flag: FLAGS[s.id.split('-')[0] ?? ''] ?? '🌱' }))
  .sort((a, b) => rank(a.scenarioId) - rank(b.scenarioId) || a.scenarioId.localeCompare(b.scenarioId))

export const languageName: Record<string, string> = { en: 'English', es: 'Español', fr: 'Français' }
