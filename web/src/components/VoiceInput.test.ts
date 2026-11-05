// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import VoiceInput from './VoiceInput.vue'
import type { VoiceClient } from '../lib/voiceClient'
import type { Recording } from '../lib/voiceRecorder'
function setup() {
  let finish!: (b: Blob) => void
  const result = new Promise<Blob>(resolve => { finish = resolve })
  const recording: Recording = { result, stop: vi.fn(async () => { finish(new Blob(['audio'], { type: 'audio/webm' })); return result }), cancel: vi.fn() }
  const service: VoiceClient = {
    create: vi.fn(async () => ({ voice_id: 'v', upload: { url: 'https://s3.test', fields: {} } })),
    upload: vi.fn(async () => {}), start: vi.fn<VoiceClient['start']>(async () => ({ status: 'pending' })),
    get: vi.fn<VoiceClient['get']>(async () => ({ status: 'done', transcript: 'Lluvia irregular.', transcript_english: 'Irregular rain.' })),
    cancel: vi.fn<VoiceClient['cancel']>(async () => ({ status: 'cancelled' })),
  }
  const w = mount(VoiceInput, { props: { apiUrl: 'https://api.test', conversationId: 'c', producerId: 'p', passcode: 'secret',
    language: 'en', disabled: false, capture: async () => recording, makeClient: () => service } })
  return { w, service, recording }
}
beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())
describe('voice input', () => {
  it('records on click, announces state and emits editable text only after transcription', async () => {
    const { w, service } = setup()
    expect(service.create).not.toHaveBeenCalled()
    await w.get('button').trigger('click'); await flushPromises()
    expect(w.get('[role="status"]').text()).toContain('Recording')
    await w.get('.btn-primary').trigger('click'); await flushPromises()
    await vi.advanceTimersByTimeAsync(2000); await flushPromises()
    expect(w.emitted('transcript')).toEqual([['Lluvia irregular.', 'Irregular rain.']])
    expect(w.text()).toContain('before sending'); w.unmount()
  })
  it('cancels recording without creating an upload', async () => {
    const { w, service, recording } = setup(); await w.get('button').trigger('click'); await flushPromises()
    await w.get('.btn-text').trigger('click')
    expect(recording.cancel).toHaveBeenCalled(); expect(service.create).not.toHaveBeenCalled(); expect(w.emitted('transcript')).toBeUndefined(); w.unmount()
  })
  it('cancels a pending job on navigation and ignores a late transcript', async () => {
    const { w, service } = setup(); await w.get('button').trigger('click'); await flushPromises()
    await w.get('.btn-primary').trigger('click'); await flushPromises()
    await w.setProps({ disabled: true }); await flushPromises(); await vi.advanceTimersByTimeAsync(2000)
    expect(service.cancel).toHaveBeenCalledWith('v'); expect(w.emitted('transcript')).toBeUndefined(); w.unmount()
  })
  it('keeps typing available and reports transcription failure', async () => {
    const { w, service } = setup(); vi.mocked(service.get).mockResolvedValue({ status: 'failed' })
    await w.get('button').trigger('click'); await flushPromises(); await w.get('.btn-primary').trigger('click'); await flushPromises()
    await vi.advanceTimersByTimeAsync(2000); await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('type your message'); expect(w.emitted('transcript')).toBeUndefined(); w.unmount()
  })
})
