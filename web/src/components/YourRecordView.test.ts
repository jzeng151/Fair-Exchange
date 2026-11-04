// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { ConversationRecord } from '../../../api/src/types/conversation-record'
import { t } from '../data/i18n'
import { saveRecord } from '../lib/demoStore'
import YourRecordView from './YourRecordView.vue'

const completed: ConversationRecord = {
  record_id: 'r1',
  producer_id: 'P-001',
  created_at: '2026-11-04T10:00:00Z',
  updated_at: '2026-11-04T10:30:00Z',
  version: 3,
  status: 'completed',
  closed_at: '2026-11-04T10:30:00Z',
  consent: { scope: 'internal', recorded_at: '2026-11-04T10:20:00Z' },
  language: 'es',
  entity_type: 'cooperative',
  summary_original: 'La lluvia bajó mucho',
  tags: ['water'],
  evidence: 'full',
  insights: [],
  peer_examples: [],
  feedback: 'yes',
  review_status: 'pending',
} as ConversationRecord

const declined: ConversationRecord = {
  record_id: 'd1',
  producer_id: 'P-001',
  created_at: '2026-11-04T11:00:00Z',
  updated_at: '2026-11-04T11:10:00Z',
  version: 1,
  status: 'declined',
  closed_at: '2026-11-04T11:10:00Z',
  consent: { scope: 'declined', recorded_at: '2026-11-04T11:05:00Z' },
} as ConversationRecord

beforeEach(() => localStorage.clear())
afterEach(() => localStorage.clear())

describe('YourRecordView', () => {
  it('shows Spanish labels for a Spanish producer', () => {
    saveRecord(completed)
    const w = mount(YourRecordView, { props: { producerId: 'P-001', lang: 'es' } })
    expect(w.text()).toContain(t.es.yourRecord.title) // "Su registro"
    expect(w.text()).toContain(t.es.yourRecord.summary) // "Su resumen"
    expect(w.text()).toContain('Agua') // the water tag, translated
  })

  it('shows the declined row text', () => {
    saveRecord(declined)
    const w = mount(YourRecordView, { props: { producerId: 'P-001', lang: 'en' } })
    expect(w.text()).toContain(t.en.yourRecord.scope.declined) // "Not stored: you declined"
  })

  it('has no edit or delete controls', () => {
    saveRecord(completed)
    const w = mount(YourRecordView, { props: { producerId: 'P-001', lang: 'en' } })
    expect(w.find('input').exists()).toBe(false)
    expect(w.find('textarea').exists()).toBe(false)
    // The only buttons are the list selectors; none edit or delete.
    const labels = w.findAll('button').map((b) => b.text().toLowerCase())
    expect(labels.some((l) => /edit|delete|save|remove|editar|eliminar|guardar|borrar/.test(l))).toBe(false)
  })

  it('shows the contact note', () => {
    saveRecord(completed)
    const w = mount(YourRecordView, { props: { producerId: 'P-001', lang: 'en' } })
    expect(w.text()).toContain(t.en.yourRecord.contact)
  })

  it('shows only the caller’s records', () => {
    saveRecord(completed)
    saveRecord({ ...completed, record_id: 'other', producer_id: 'P-002' } as ConversationRecord)
    const w = mount(YourRecordView, { props: { producerId: 'P-001', lang: 'en' } })
    expect(w.text()).toContain('La lluvia bajó mucho')
    // Exactly one record row for this producer.
    expect(w.findAll('.record-list li')).toHaveLength(1)
  })
})
