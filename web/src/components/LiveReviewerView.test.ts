// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CompletedRecord } from '../../../api/src/types/conversation-record'
import { demoRecords } from '../lib/demoSeed'
import { RecordApiError } from '../lib/recordApi'
import LiveReviewerView from './LiveReviewerView.vue'
const mocks = vi.hoisted(() => ({ identity: vi.fn(), list: vi.fn(), get: vi.fn(), patch: vi.fn(), approve: vi.fn() }))
vi.mock('../lib/recordApi', async (original) => ({ ...await original<object>(), recordApi: () => mocks }))
let record: CompletedRecord
beforeEach(() => {
  vi.resetAllMocks()
  const completed = demoRecords(new Date()).records.find((r): r is CompletedRecord => r.status === 'completed')!
  record = { ...completed, review_status: 'pending', pii_flag: false, pii_review: null, reviewer_tags: null,
    reviewer_summary_original: null, reviewer_summary_english: null }
  mocks.identity.mockResolvedValue({ user_id: 'demo:reviewer', roles: ['reviewer'] })
  mocks.list.mockResolvedValue({ records: [record] })
  mocks.get.mockImplementation(async () => record)
})
async function open() {
  const w = mount(LiveReviewerView, { props: { apiUrl: 'https://api.example.test' } })
  await w.get('input[type="password"]').setValue('test-passcode')
  await w.get('form.signin').trigger('submit'); await flushPromises()
  await w.get('.record-list button').trigger('click'); await flushPromises()
  return w
}
describe('live reviewer', () => {
  it('retains unsaved corrections on conflict and reloads explicitly', async () => {
    const w = await open()
    await w.get('textarea').setValue('Unsaved correction')
    mocks.patch.mockRejectedValue(new RecordApiError(409))
    await w.findAll('button').find((b) => b.text() === 'Save corrections')!.trigger('click'); await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('This record changed')
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('Unsaved correction')
    await w.findAll('button').find((b) => b.text() === 'Reload record')!.trigger('click'); await flushPromises()
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe(record.summary_original)
  })
  it('blocks approval for unresolved PII and shows matches with context', async () => {
    record.pii_flag = true
    record.pii_matches = [{ entity_type: 'NAME', text: 'Test Person', context: '[Synthetic] Test Person mentioned', message_at: record.created_at }]
    const w = await open()
    expect(w.text()).toContain('[Synthetic] Test Person mentioned')
    expect(w.findAll('button').find((b) => b.text() === 'Approve record')!.attributes('disabled')).toBeDefined()
  })
  it('shows the decision log, or says it is empty', async () => {
    record.decision_log = [{ at: record.created_at, kind: 'verifier', code: 'clause_not_retrieved', refs: ['RF-F8C4E1', 'APS 2.1.1'] }]
    const w = await open()
    expect(w.text()).toContain('Decision log')
    expect(w.text()).toContain('verifier · clause_not_retrieved · RF-F8C4E1, APS 2.1.1')
    record.decision_log = []
    expect((await open()).text()).toContain('No decisions logged')
  })
  it('makes approved records read-only', async () => {
    record.review_status = 'reviewed'
    const w = await open()
    expect(w.get('textarea').attributes('readonly')).toBeDefined()
    expect(w.findAll('button').some((b) => b.text() === 'Approve record')).toBe(false)
  })
  it('does not load reviewer data for a producer identity', async () => {
    mocks.identity.mockResolvedValue({ roles: ['producer'] })
    const w = mount(LiveReviewerView, { props: { apiUrl: 'https://api.example.test' } })
    await w.get('form.signin').trigger('submit'); await flushPromises()
    expect(mocks.list).not.toHaveBeenCalled()
    expect(w.text()).toContain('reviewer sign-in is required')
  })
})
