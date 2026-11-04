// "Load demo records" (issue #31): a few SYNTHETIC records so the reviewer view always has something
// to show, covering each state: pending, personal-info flag, English, and a decline.
import type { ConversationRecord } from '../../../api/src/types/conversation-record'
import { scenarios } from '../data/scenarios'
import { toClaims } from './claims'
import type { TraceStep } from './demoStore'
import { buildCompletedRecord, buildDeclinedRecord } from './record'

function trace(producerId: string, region: string, at: Date): TraceStep[] {
  const t = (s: number) => new Date(at.getTime() - (60 - s) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return [
    { time: t(0), tool: 'session.start', detail: `Session bound to producer ${producerId} (${region}). Tools read producer ID from session only.` },
    { time: t(20), tool: 'agent.playback', detail: 'Playing back understanding. No tools called until producer confirms.' },
    { time: t(30), tool: 'get_producer_record', detail: `producer_id=${producerId} (from session)` },
    { time: t(32), tool: 'get_regional_context', detail: `region=${region} (from session)` },
    { time: t(34), tool: 'find_peer_examples', detail: 'Matched on crop, entity type and challenge tags' },
    { time: t(36), tool: 'check_standards', detail: 'Every claim cites a real APS/FPS clause' },
    { time: t(50), tool: 'write_back_record', detail: 'Record saved with consent (demo mode), review_status=pending' },
  ]
}

export function demoRecords(now: Date): { records: ConversationRecord[]; traces: Record<string, TraceStep[]> } {
  const [cauca, oaxaca, soubre] = scenarios
  if (!cauca || !oaxaca || !soubre) throw new Error('demo scenarios missing')
  const minutesAgo = (m: number) => new Date(now.getTime() - m * 60_000)

  const es = toClaims(cauca, 'es')
  const caucaRecord = buildCompletedRecord({
    recordId: 'DEMO-001', producerId: cauca.id, now: minutesAgo(42), language: 'es', entityType: cauca.entityType,
    summaryOriginal: 'La lluvia ha sido muy irregular y la cosecha bajó. Puede llamar a Don Ernesto al +57 312 555 0199.',
    summaryEnglish: 'Rainfall has been very irregular and the harvest dropped. You can call Don Ernesto at +57 312 555 0199.',
    tags: cauca.tags, insights: es.insights, peerExamples: es.peerExamples, feedback: 'yes', piiFlag: true,
  })
  const en = toClaims(oaxaca, 'en')
  const oaxacaRecord = buildCompletedRecord({
    recordId: 'DEMO-002', producerId: oaxaca.id, now: minutesAgo(18), language: 'en', entityType: oaxaca.entityType,
    summaryOriginal: 'The price we get for our coffee has dropped a lot and members are struggling to cover costs.',
    summaryEnglish: '', tags: oaxaca.tags, insights: en.insights, peerExamples: en.peerExamples, feedback: 'somewhat', piiFlag: false,
  })
  const declined = buildDeclinedRecord({ recordId: 'DEMO-003', producerId: soubre.id, now: minutesAgo(7) })

  return {
    records: [declined, oaxacaRecord, caucaRecord],
    traces: {
      [caucaRecord.record_id]: [...trace(cauca.id, cauca.region, minutesAgo(42)).slice(0, 1),
        { time: '', tool: 'comprehend.detectPii (simulated)', detail: 'PII-like content found → record flagged for human review. No redaction.' },
        ...trace(cauca.id, cauca.region, minutesAgo(42)).slice(1)],
      [oaxacaRecord.record_id]: trace(oaxaca.id, oaxaca.region, minutesAgo(18)),
    },
  }
}
