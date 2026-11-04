// "Load sample data" for the admin dashboard (issue #33). A few demo conversations can't clear the
// n < 5 rule, so this adds SYNTHETIC records (IDs start with SEED-). Deterministic: the same records
// every time, so the demo is repeatable. Stand-in for #37 (seeded records in the real store).
import type { CompletedRecord, ConversationRecord } from '../../../api/src/types/conversation-record'
import { CHALLENGE_TAGS, type ChallengeTag } from '../data/scenarios'
import { buildCompletedRecord, buildDeclinedRecord } from './record'

/** Small seeded random generator (mulberry32), so output never changes between runs. */
function rng(seed: number) {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
function pick<T>(r: () => number, weighted: [T, number][]): T {
  const total = weighted.reduce((s, [, w]) => s + w, 0)
  let x = r() * total
  for (const [v, w] of weighted) if ((x -= w) < 0) return v
  return weighted[weighted.length - 1]![0]
}

// Weighted so common challenges clear n >= 5 and rare ones stay hidden, as real data would.
const TAG_WEIGHTS: [ChallengeTag, number][] = [
  ['climate and weather', 14], ['water', 10], ['market and price', 12], ['labor and migration', 7],
  ['financial and access to capital', 6], ['soil and land', 5], ['infrastructure', 3], ['health', 1],
  ['education', 1], ['biodiversity and conservation', 1], ['social and community', 1],
]
const LANGS: [string, number][] = [['es', 5], ['en', 3], ['fr', 2]]
const ENTITIES: [string, number][] = [['cooperative', 6], ['estate', 3], ['smallholder group', 2]]
const FEEDBACK: [CompletedRecord['feedback'], number][] = [['yes', 5], ['somewhat', 3], ['no', 1], [null, 2]]

const SUMMARY: Record<string, { es: string; en: string; fr: string }> = {
  default: { es: 'Este año ha sido difícil para la organización.', en: 'This year has been difficult for the organization.', fr: 'Cette année a été difficile pour l’organisation.' },
  'climate and weather': { es: 'Las lluvias llegaron tarde y la cosecha bajó.', en: 'The rains came late and the harvest fell.', fr: 'Les pluies sont arrivées tard et la récolte a baissé.' },
  water: { es: 'Falta agua para el beneficio en la temporada seca.', en: 'There is not enough water for processing in the dry season.', fr: 'Il manque de l’eau pour le traitement en saison sèche.' },
  'market and price': { es: 'El precio que recibimos bajó y cuesta cubrir los costos.', en: 'The price we receive dropped and costs are hard to cover.', fr: 'Le prix reçu a baissé et les coûts sont difficiles à couvrir.' },
  'labor and migration': { es: 'Cuesta encontrar trabajadores para la cosecha.', en: 'It is hard to find workers for the harvest.', fr: 'Il est difficile de trouver des travailleurs pour la récolte.' },
}

export function dashboardRecords(now: Date): ConversationRecord[] {
  const r = rng(20261105)
  const out: ConversationRecord[] = []
  for (let i = 1; i <= 60; i++) {
    const recordId = `SEED-${String(i).padStart(3, '0')}`
    const producerId = `P-S${String(100 + Math.floor(r() * 40)).padStart(3, '0')}`
    const at = new Date(now.getTime() - Math.floor(r() * 30 * 24 * 60) * 60_000) // last 30 days
    if (r() < 0.12) { out.push(buildDeclinedRecord({ recordId, producerId, now: at })); continue }

    const first = pick(r, TAG_WEIGHTS)
    const second = r() < 0.4 ? pick(r, TAG_WEIGHTS.filter(([t]) => t !== first)) : null
    const tags = (second ? [first, second] : [first]).filter((t) => (CHALLENGE_TAGS as readonly string[]).includes(t))
    const language = pick(r, LANGS)
    const text = SUMMARY[first] ?? SUMMARY.default!
    const base = buildCompletedRecord({
      recordId, producerId, now: at, language, entityType: pick(r, ENTITIES),
      summaryOriginal: text[language as 'es' | 'en' | 'fr'], summaryEnglish: text.en,
      tags: tags as CompletedRecord['tags'], insights: [], peerExamples: [], feedback: pick(r, FEEDBACK), piiFlag: false,
    })
    out.push(r() < 0.75 ? { ...base, review_status: 'reviewed', reviewed_by: 'IRL reviewer (sample)', reviewed_at: now.toISOString() } : base)
  }
  return out
}
