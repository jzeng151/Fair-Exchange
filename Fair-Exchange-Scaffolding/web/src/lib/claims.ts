// Scenario evidence -> #6 schema claims (shared by the chat and the demo records)
import type { Claim } from '../../../../api/src/types/conversation-record'
import type { Lang } from '../data/i18n'
import type { Scenario } from '../data/scenarios'

export function toClaims(s: Scenario, lang: Lang): { insights: Claim[]; peerExamples: Claim[] } {
  return {
    insights: s.insights.map((i) => ({
      text: i.text[lang] ?? i.text.en,
      citation: { source: i.source, standard_clause: i.clause, strength: i.strength, period: i.period },
    })),
    peerExamples: s.peers.map((p) => ({
      text: p.text[lang] ?? p.text.en,
      citation: { source: `${p.org} (${p.place})`, standard_clause: p.clause, strength: 'nearest', period: null },
    })),
  }
}
