// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LiveChatView from './LiveChatView.vue'
import { LiveError } from '../lib/liveClient'
import type { ActionName, LiveClient, ResumeResponse, StreamEvent } from '../lib/liveClient'

const cite = (source: string) => ({ source, standard_clause: 'APS 2.4.2.a', period: '2024-2025', strength: 'exact' as const })
const step = (s: string, allowed: ActionName[], language = 'es'): StreamEvent[] => [
  { type: 'step', seq: 90, step: s as never, language },
  { type: 'actions', seq: 91, allowed, language },
  { type: 'done', seq: 92 },
]

/** A scripted chat API: records every call and answers with canned events. */
function fakeClient(script: { start?: StreamEvent[]; message?: StreamEvent[][]; action?: Record<string, StreamEvent[]>; resume?: ResumeResponse | Error } = {}) {
  const calls: unknown[][] = []
  let m = 0
  async function* gen(events: StreamEvent[] | Error) {
    if (events instanceof Error) throw events
    for (const e of events) yield e
  }
  const client: LiveClient = {
    start: () => { calls.push(['start']); return gen(script.start ?? [{ type: 'conversation', conversationId: 'c-1' }, { type: 'text', seq: 1, text: '¿Qué ha sido lo más difícil?' }, ...step('intake', ['end'])]) },
    message: (id, text) => { calls.push(['message', id, text]); return gen(script.message?.[m++] ?? step('intake', ['end'])) },
    action: (id, name, args = {}) => { calls.push(['action', id, name, args]); return gen(script.action?.[name] ?? step('consent', ['set_consent', 'end'])) },
    resume: async (id) => { calls.push(['resume', id]); if (script.resume instanceof Error) throw script.resume; return script.resume! },
  }
  return { client, calls }
}

async function open(fake: ReturnType<typeof fakeClient>) {
  const w = mount(LiveChatView, { props: { apiUrl: 'http://api.test', makeClient: () => fake.client } })
  await w.get('[data-producer="CFC19603C1B7B29C017954FD1DB2D620"]').trigger('click')
  await flushPromises()
  return w
}
const bubbles = (w: ReturnType<typeof mount>) => w.findAll('.msg').map((b) => b.text())

afterEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })

describe('LiveChatView', () => {
  it("starts a conversation for the picked producer and shows FEX's first question", async () => {
    const fake = fakeClient()
    const w = await open(fake)
    expect(fake.calls).toEqual([['start']])
    expect(bubbles(w)).toEqual(['¿Qué ha sido lo más difícil?'])
  })

  it("sends the producer's message to the conversation and shows both sides", async () => {
    const fake = fakeClient({ message: [[{ type: 'text', seq: 1, text: '¿Cuándo empezó?' }, ...step('intake', ['end'])]] })
    const w = await open(fake)
    await w.get('#live-msg').setValue('La lluvia bajó')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(fake.calls.at(-1)).toEqual(['message', 'c-1', 'La lluvia bajó'])
    expect(bubbles(w)).toEqual(['¿Qué ha sido lo más difícil?', 'La lluvia bajó', '¿Cuándo empezó?'])
  })

  it('shows "That\'s right" on the playback and sends confirm_playback as an action, not chat text (#13)', async () => {
    const fake = fakeClient({
      start: [{ type: 'conversation', conversationId: 'c-1' }, { type: 'text', seq: 1, text: 'Esto es lo que entendí…' }, ...step('playback', ['confirm_playback', 'correct_playback', 'end'])],
      action: { confirm_playback: [
        { type: 'text', seq: 1, text: 'Esto es lo que encontré.' },
        { type: 'claim', seq: 2, section: 'insights', claim: { text: 'La lluvia bajó 11.5%.', citation: cite('CHIRPS v2.0 rainfall') } },
        { type: 'claim', seq: 3, section: 'peer_examples', claim: { text: 'Un grupo instaló riego.', citation: cite('FTUSA Premium project') } },
        { type: 'answer', seq: 4, insights: [], peer_examples: [], evidence: 'full' },
        ...step('consent', ['reopen_playback', 'set_consent', 'end']),
      ] },
    })
    const w = await open(fake)
    const confirm = w.findAll('button').find((b) => b.text() === 'Es correcto')!
    await confirm.trigger('click')
    await flushPromises()
    expect(fake.calls.at(-1)).toEqual(['action', 'c-1', 'confirm_playback', {}])
    const cards = w.findAll('.claim')
    expect(cards.map((c) => c.attributes('data-section'))).toEqual(['insights', 'peer_examples'])
    expect(cards[0]!.text()).toContain('CHIRPS v2.0 rainfall')
    expect(cards[0]!.text()).toContain('APS 2.4.2.a')
    expect(w.findAll('.claim-heading').map((h) => h.text())).toEqual(['Lo que muestran los datos', 'Lo que otros han probado'])
  })

  it('sends the consent choice and shows the saved record', async () => {
    const fake = fakeClient({
      start: [{ type: 'conversation', conversationId: 'c-1' }, ...step('consent', ['reopen_playback', 'set_consent', 'end'])],
      action: { set_consent: [{ type: 'record_saved', seq: 1, status: 'completed', consent_scope: 'internal', version: 1 }, ...step('feedback', ['reopen_playback', 'set_consent', 'set_feedback', 'end'])] },
    })
    const w = await open(fake)
    await w.get('[data-consent="internal"]').trigger('click')
    await flushPromises()
    expect(fake.calls.at(-1)).toEqual(['action', 'c-1', 'set_consent', { scope: 'internal' }])
    expect(w.text()).toContain('Guardado (versión 1).')
    expect(w.find('[data-feedback="yes"]').exists()).toBe(true)
  })

  it('in the feedback step the consent choice shrinks to one line but stays changeable (#19)', async () => {
    const fake = fakeClient({
      start: [{ type: 'conversation', conversationId: 'c-1' }, ...step('consent', ['reopen_playback', 'set_consent', 'end'])],
      action: {
        set_consent: [{ type: 'record_saved', seq: 1, status: 'completed', consent_scope: 'internal_and_outward', version: 1 }, ...step('feedback', ['reopen_playback', 'set_consent', 'set_feedback', 'end'])],
      },
    })
    const w = await open(fake)
    await w.get('[data-consent="internal_and_outward"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-consent="internal"]').exists()).toBe(false)
    expect(w.get('.consent-line').text()).toContain('Sí, y se puede compartir')
    await w.get('[data-action="change-consent"]').trigger('click')
    expect(w.get('[data-consent="internal_and_outward"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-consent="declined"]').trigger('click')
    await flushPromises()
    expect(fake.calls.at(-1)).toEqual(['action', 'c-1', 'set_consent', { scope: 'declined' }])
  })

  it('after a feedback answer the question collapses to a thank-you line, still changeable (#23)', async () => {
    const feedbackStep = step('feedback', ['reopen_playback', 'set_consent', 'set_feedback', 'end'])
    const saved = (version: number): StreamEvent => ({ type: 'record_saved', seq: 1, status: 'completed', consent_scope: 'internal', version })
    const fake = fakeClient({
      start: [{ type: 'conversation', conversationId: 'c-1' }, ...feedbackStep],
      action: { set_feedback: [saved(2), ...feedbackStep] },
    })
    const w = await open(fake)
    await w.get('[data-feedback="somewhat"]').trigger('click')
    await flushPromises()
    expect(fake.calls.at(-1)).toEqual(['action', 'c-1', 'set_feedback', { value: 'somewhat' }])
    expect(w.find('[data-feedback="yes"]').exists()).toBe(false)
    expect(w.get('.feedback-line').text()).toContain('Gracias')
    expect(w.get('.feedback-line').text()).toContain('Algo')
    await w.get('[data-action="change-feedback"]').trigger('click')
    expect(w.get('[data-feedback="somewhat"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-feedback="no"]').trigger('click')
    await flushPromises()
    expect(fake.calls.at(-1)).toEqual(['action', 'c-1', 'set_feedback', { value: 'no' }])
    expect(w.find('[data-feedback="yes"]').exists()).toBe(false)
    expect(w.get('.feedback-line').text()).toContain('No')
  })

  it('a feedback answer that fails to save keeps the question open', async () => {
    const feedbackStep = step('feedback', ['reopen_playback', 'set_consent', 'set_feedback', 'end'])
    const fake = fakeClient({
      start: [{ type: 'conversation', conversationId: 'c-1' }, ...feedbackStep],
      action: { set_feedback: [{ type: 'error', seq: 1, code: 'agent_failed', message: 'No se pudo guardar.' }, ...feedbackStep] },
    })
    const w = await open(fake)
    await w.get('[data-feedback="yes"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-feedback="yes"]').exists()).toBe(true)
    expect(w.find('.feedback-line').exists()).toBe(false)
  })

  it('a feedback answer whose request fails keeps the question open', async () => {
    const fake = fakeClient({ start: [{ type: 'conversation', conversationId: 'c-1' }, ...step('feedback', ['set_feedback', 'end'])] })
    fake.client.action = () => (async function* () { throw new LiveError(0, 'unreachable') })()
    const w = await open(fake)
    await w.get('[data-feedback="yes"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-feedback="yes"]').exists()).toBe(true)
    expect(w.find('.feedback-line').exists()).toBe(false)
  })

  it("a feedback answer still saving for one producer is never shown as another producer's answer", async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    const feedbackStart = (id: string) => [{ type: 'conversation', conversationId: id } as StreamEvent, ...step('feedback', ['set_feedback', 'end'])]
    const clients: Record<string, LiveClient> = {
      CFC19603C1B7B29C017954FD1DB2D620: { ...fakeClient({ start: feedbackStart('c-A') }).client, action: async function* () {
        await gate
        for (const e of step('feedback', ['set_feedback', 'end'])) yield e
      } },
      A7F700B04BCE55512CB026A71121426C: fakeClient({ start: feedbackStart('c-B') }).client,
    }
    const w = mount(LiveChatView, { props: { apiUrl: 'http://api.test', makeClient: (id: string) => clients[id]! } })
    await w.get('[data-producer="CFC19603C1B7B29C017954FD1DB2D620"]').trigger('click')
    await flushPromises()
    await w.get('[data-feedback="yes"]').trigger('click')
    await w.get('.back-link').trigger('click')
    await w.get('[data-producer="A7F700B04BCE55512CB026A71121426C"]').trigger('click')
    await flushPromises()
    release() // A's feedback request finishes after B's conversation has loaded
    await flushPromises()
    expect(w.find('[data-feedback="yes"]').exists()).toBe(true)
    expect(w.find('.feedback-line').exists()).toBe(false)
  })

  it('asks before ending, and does nothing if the producer cancels (#13)', async () => {
    const fake = fakeClient()
    const w = await open(fake)
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    await w.get('[data-action="end"]').trigger('click')
    await flushPromises()
    expect(fake.calls.some((c) => c[2] === 'end')).toBe(false)
  })

  it('shows a readable notice when the API is busy (409) instead of breaking', async () => {
    const fake = fakeClient()
    fake.client.message = () => (async function* () { throw new LiveError(409, 'A turn is in progress') })()
    const w = await open(fake)
    await w.get('#live-msg').setValue('hola')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.get('.alert').text()).toContain('FEX todavía está respondiendo')
    expect((w.get('#live-msg').element as HTMLInputElement).disabled).toBe(false)
  })

  it('resumes the saved conversation for this producer after a reload instead of starting a new one', async () => {
    sessionStorage.setItem('fex.live.CFC19603C1B7B29C017954FD1DB2D620', 'c-old')
    const fake = fakeClient({ resume: { step: 'feedback', language: 'es', allowed: ['set_feedback', 'end'], answer: null, history: [{ role: 'fex', text: 'Hola de nuevo', at: '2026-11-04T10:00:00Z' }] } })
    const w = await open(fake)
    expect(fake.calls).toEqual([['resume', 'c-old']])
    expect(bubbles(w)).toEqual(['Hola de nuevo'])
  })

  it('after a reload in the feedback step, consent can still be changed even though the choice is not known (#19)', async () => {
    sessionStorage.setItem('fex.live.CFC19603C1B7B29C017954FD1DB2D620', 'c-old')
    const fake = fakeClient({ resume: { step: 'feedback', language: 'es', allowed: ['reopen_playback', 'set_consent', 'set_feedback', 'end'], answer: null, history: [] } })
    const w = await open(fake)
    await w.get('[data-action="change-consent"]').trigger('click')
    expect(w.findAll('[data-consent]').length).toBe(3)
  })

  it('keeps the saved conversation and offers a retry when resuming fails for a temporary reason', async () => {
    sessionStorage.setItem('fex.live.CFC19603C1B7B29C017954FD1DB2D620', 'c-old')
    const fake = fakeClient({ resume: new LiveError(0, 'unreachable') })
    const w = await open(fake)
    expect(fake.calls).toEqual([['resume', 'c-old']]) // no new conversation started
    expect(sessionStorage.getItem('fex.live.CFC19603C1B7B29C017954FD1DB2D620')).toBe('c-old')
    // Nothing from the conversation has loaded yet, so its language is unknown: the notice is in English
    expect(w.get('.alert').text()).toContain('Can’t reach FEX')
    fake.client.resume = async (id) => { fake.calls.push(['resume', id]); return { step: 'intake', language: 'es', allowed: ['end'], answer: null, history: [{ role: 'fex', text: 'Hola otra vez', at: '2026-11-04T10:00:00Z' }] } }
    await w.get('[data-action="retry-resume"]').trigger('click')
    await flushPromises()
    expect(fake.calls.at(-1)).toEqual(['resume', 'c-old'])
    expect(bubbles(w)).toEqual(['Hola otra vez'])
  })

  it("a reply still streaming for one producer never reaches another producer's chat", async () => {
    let release!: () => void, releaseB!: () => void
    const gate = new Promise<void>((r) => { release = r })
    const gateB = new Promise<void>((r) => { releaseB = r })
    const clients: Record<string, LiveClient> = {
      CFC19603C1B7B29C017954FD1DB2D620: { ...fakeClient().client, start: async function* () {
        yield { type: 'conversation', conversationId: 'c-A' } as StreamEvent
        await gate
        yield { type: 'text', seq: 1, text: 'late reply for A' } as StreamEvent
        yield { type: 'done', seq: 2 } as StreamEvent
      } },
      A7F700B04BCE55512CB026A71121426C: { ...fakeClient().client, start: async function* () {
        await gateB
        for (const e of [{ type: 'conversation', conversationId: 'c-B' }, { type: 'text', seq: 1, text: 'hello B' }, ...step('intake', ['end'])]) yield e as StreamEvent
      } },
    }
    const w = mount(LiveChatView, { props: { apiUrl: 'http://api.test', makeClient: (id: string) => clients[id]! } })
    await w.get('[data-producer="CFC19603C1B7B29C017954FD1DB2D620"]').trigger('click')
    await flushPromises()
    await w.get('.back-link').trigger('click')
    await w.get('[data-producer="A7F700B04BCE55512CB026A71121426C"]').trigger('click')
    await flushPromises()
    release() // A's late reply finishes while B's first reply is still loading
    await flushPromises()
    expect(w.find('.typing').exists()).toBe(true) // B is still busy: A's cleanup must not touch B's view
    expect((w.get('#live-msg').element as HTMLInputElement).disabled).toBe(true)
    releaseB()
    await flushPromises()
    expect(bubbles(w)).toEqual(['hello B'])
    expect(sessionStorage.getItem('fex.live.A7F700B04BCE55512CB026A71121426C')).toBe('c-B')
  })

  it('starts fresh when the saved conversation is gone (404)', async () => {
    sessionStorage.setItem('fex.live.CFC19603C1B7B29C017954FD1DB2D620', 'c-gone')
    const fake = fakeClient({ resume: new LiveError(404, 'Not found') })
    await open(fake)
    expect(fake.calls).toEqual([['resume', 'c-gone'], ['start']])
  })
})
