import VoiceInput from './VoiceInput.vue'
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
  await w.get('[data-scenario="S1"]').trigger('click')
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
      'SYN-001': { ...fakeClient({ start: feedbackStart('c-A') }).client, action: async function* () {
        await gate
        for (const e of step('feedback', ['set_feedback', 'end'])) yield e
      } },
      'SYN-002': fakeClient({ start: feedbackStart('c-B') }).client,
    }
    const w = mount(LiveChatView, { props: { apiUrl: 'http://api.test', makeClient: (id: string) => clients[id]! } })
    await w.get('[data-scenario="S1"]').trigger('click')
    await flushPromises()
    await w.get('[data-feedback="yes"]').trigger('click')
    await w.get('.back-link').trigger('click')
    await w.get('[data-scenario="S2"]').trigger('click')
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

  it('keeps two scenarios that share a producer apart (S5 and S7, #35)', async () => {
    const fake = fakeClient()
    const made: string[] = []
    const w = mount(LiveChatView, { props: { apiUrl: 'http://api.test', makeClient: (id: string) => { made.push(id); return fake.client } } })
    const s5 = w.get('[data-scenario="S5"]'), s7 = w.get('[data-scenario="S7"]')
    expect(s5.attributes('data-producer')).toBe(s7.attributes('data-producer'))
    await s7.trigger('click')
    await flushPromises()
    expect(made).toEqual([s7.attributes('data-producer')])
    expect(w.text()).toContain('contrast partner of S1')
    expect(sessionStorage.getItem('fex.live.S7')).toBe('c-1')
    expect(sessionStorage.getItem('fex.live.S5')).toBeNull()
  })

  it('resumes the saved conversation for this producer after a reload instead of starting a new one', async () => {
    sessionStorage.setItem('fex.live.S1', 'c-old')
    const fake = fakeClient({ resume: { step: 'feedback', language: 'es', allowed: ['set_feedback', 'end'], answer: null, history: [{ role: 'fex', text: 'Hola de nuevo', at: '2026-11-04T10:00:00Z' }] } })
    const w = await open(fake)
    expect(fake.calls).toEqual([['resume', 'c-old']])
    expect(bubbles(w)).toEqual(['Hola de nuevo'])
  })

  it('after a reload in the feedback step, consent can still be changed even though the choice is not known (#19)', async () => {
    sessionStorage.setItem('fex.live.S1', 'c-old')
    const fake = fakeClient({ resume: { step: 'feedback', language: 'es', allowed: ['reopen_playback', 'set_consent', 'set_feedback', 'end'], answer: null, history: [] } })
    const w = await open(fake)
    await w.get('[data-action="change-consent"]').trigger('click')
    expect(w.findAll('[data-consent]').length).toBe(3)
  })

  it('keeps the saved conversation and offers a retry when resuming fails for a temporary reason', async () => {
    sessionStorage.setItem('fex.live.S1', 'c-old')
    const fake = fakeClient({ resume: new LiveError(0, 'unreachable') })
    const w = await open(fake)
    expect(fake.calls).toEqual([['resume', 'c-old']]) // no new conversation started
    expect(sessionStorage.getItem('fex.live.S1')).toBe('c-old')
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
      'SYN-001': { ...fakeClient().client, start: async function* () {
        yield { type: 'conversation', conversationId: 'c-A' } as StreamEvent
        await gate
        yield { type: 'text', seq: 1, text: 'late reply for A' } as StreamEvent
        yield { type: 'done', seq: 2 } as StreamEvent
      } },
      'SYN-002': { ...fakeClient().client, start: async function* () {
        await gateB
        for (const e of [{ type: 'conversation', conversationId: 'c-B' }, { type: 'text', seq: 1, text: 'hello B' }, ...step('intake', ['end'])]) yield e as StreamEvent
      } },
    }
    const w = mount(LiveChatView, { props: { apiUrl: 'http://api.test', makeClient: (id: string) => clients[id]! } })
    await w.get('[data-scenario="S1"]').trigger('click')
    await flushPromises()
    await w.get('.back-link').trigger('click')
    await w.get('[data-scenario="S2"]').trigger('click')
    await flushPromises()
    release() // A's late reply finishes while B's first reply is still loading
    await flushPromises()
    expect(w.find('.typing').exists()).toBe(true) // B is still busy: A's cleanup must not touch B's view
    expect((w.get('#live-msg').element as HTMLInputElement).disabled).toBe(true)
    releaseB()
    await flushPromises()
    expect(bubbles(w)).toEqual(['hello B'])
    expect(sessionStorage.getItem('fex.live.S2')).toBe('c-B')
  })

  it('starts fresh when the saved conversation is gone (404)', async () => {
    sessionStorage.setItem('fex.live.S1', 'c-gone')
    const fake = fakeClient({ resume: new LiveError(404, 'Not found') })
    await open(fake)
    expect(fake.calls).toEqual([['resume', 'c-gone'], ['start']])
  })
})

it('places the voice transcript in the editable composer without sending it', async () => {
  const fake = fakeClient()
  const w = await open(fake)
  await w.get('#live-msg').setValue('Existing draft.')
  w.getComponent(VoiceInput).vm.$emit('transcript', 'Lluvia irregular.', 'Irregular rain.')
  await flushPromises()
  expect((w.get('#live-msg').element as HTMLTextAreaElement).value).toBe('Existing draft.\nLluvia irregular.')
  expect(fake.calls).toEqual([['start']])
  await w.get('form').trigger('submit'); await flushPromises()
  expect(fake.calls.at(-1)).toEqual(['message', 'c-1', 'Existing draft.\nLluvia irregular.'])
  w.unmount()
})

describe('LiveChatView: clearer answers (#169)', () => {
  const answer = (sources: string[]): StreamEvent[] => [
    { type: 'text', seq: 1, text: 'Esto es lo que encontré.' },
    ...sources.map((s, i): StreamEvent => ({ type: 'claim', seq: 2 + i, section: i === 0 ? 'insights' : 'peer_examples', claim: { text: `Dato ${i + 1}.`, citation: cite(s) } })),
    { type: 'answer', seq: 9, insights: [], peer_examples: [], evidence: 'full' },
    ...step('consent', ['reopen_playback', 'set_consent', 'end']),
  ]

  it('numbers answer cards across both sections and restarts the numbers for a new answer', async () => {
    const fake = fakeClient({
      start: [{ type: 'conversation', conversationId: 'c-1' }, ...step('playback', ['confirm_playback', 'end'])],
      action: { confirm_playback: answer(['WRI Aqueduct 4.0 water stress', 'FTUSA Premium project']) },
      message: [answer(['World Bank Pink Sheet'])],
    })
    const w = await open(fake)
    await w.get('[data-action="confirm_playback"]').trigger('click')
    await flushPromises()
    await w.get('#live-msg').setValue('Otra pregunta')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.findAll('.claim .cite').map((c) => c.text().slice(0, 3))).toEqual(['[1]', '[2]', '[1]'])
  })

  it('marks WRI Aqueduct sources as listed in the TNFD Tools Catalogue, in the conversation language', async () => {
    const fake = fakeClient({
      start: [{ type: 'conversation', conversationId: 'c-1' }, ...step('playback', ['confirm_playback', 'end'])],
      action: { confirm_playback: answer(['WRI Aqueduct 4.0 water stress', 'FTUSA Premium project']) },
    })
    const w = await open(fake)
    await w.get('[data-action="confirm_playback"]').trigger('click')
    await flushPromises()
    const cites = w.findAll('.claim .cite').map((c) => c.text())
    expect(cites[0]).toContain('Incluido en el catálogo de herramientas de la TNFD')
    expect(cites[1]).not.toContain('TNFD')
  })

  it('explains who can see each consent choice, in the conversation language', async () => {
    const fake = fakeClient({ start: [{ type: 'conversation', conversationId: 'c-1' }, ...step('consent', ['reopen_playback', 'set_consent', 'end'])] })
    const w = await open(fake)
    const lines = w.findAll('.consent-explainer li').map((l) => l.text())
    expect(lines).toHaveLength(3)
    expect(lines[0]).toContain('equipo de Fair Trade USA')
    expect(lines[1]).toContain('nunca con su nombre')
    expect(lines[2]).toContain('no se guarda nada')
  })
})

describe('LiveChatView: Listen and attachments (#169)', () => {
  it("reads a FEX reply aloud through the speech route for this producer's conversation", async () => {
    const fake = fakeClient()
    const speak = vi.fn(async () => new Blob(['mp3'], { type: 'audio/mpeg' }))
    const made: [string, string][] = []
    const w = mount(LiveChatView, { props: { apiUrl: 'http://api.test', makeClient: () => fake.client,
      makeSpeech: (producerId: string, conversationId: string) => { made.push([producerId, conversationId]); return { speak } } } })
    await w.get('[data-scenario="S1"]').trigger('click')
    await flushPromises()
    const listen = w.get('.msg.agent + [data-action="listen"]')
    expect(listen.text()).toContain('Escuchar')
    await listen.trigger('click')
    await flushPromises()
    expect(speak).toHaveBeenCalledWith('¿Qué ha sido lo más difícil?')
    expect(made[0]![1]).toBe('c-1')
    await w.get('#live-msg').setValue('La lluvia bajó')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(bubbles(w)).toEqual(['¿Qué ha sido lo más difícil?', 'La lluvia bajó'])
    expect(w.findAll('[data-action="listen"]')).toHaveLength(1) // FEX's words only, not the producer's
  })

  it("puts an attachment's description in the message box without sending it", async () => {
    const fake = fakeClient()
    const w = mount(LiveChatView, { props: { apiUrl: 'http://api.test', makeClient: () => fake.client } })
    await w.get('[data-scenario="S1"]').trigger('click')
    await flushPromises()
    await w.get('#live-msg').setValue('Mire esto')
    w.findComponent({ name: 'AttachInput' }).vm.$emit('description', '[Foto: Hojas secas.]')
    await flushPromises()
    expect((w.get('#live-msg').element as HTMLTextAreaElement).value).toBe('Mire esto\n[Foto: Hojas secas.]')
    expect(fake.calls).toEqual([['start']])
  })
})
