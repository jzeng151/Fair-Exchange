import { describe, expect, it } from 'vitest'
import events from '../../../api/src/core/fixtures/agent-stream.events.json'
import { apply, beginTurn, fromResume, newView, said } from './liveView'
import type { StreamEvent } from './liveClient'
import type { LiveView } from './liveView'

const claim = (text: string) => ({ text, citation: { source: 'S', standard_clause: 'APS 1.1.1', period: null, strength: 'exact' as const } })

function run(view = newView(), list: object[]) {
  for (const e of list) apply(view, e as StreamEvent)
  return view
}

describe('live view', () => {
  it('joins streamed text pieces into one FEX bubble', () => {
    const v = run(newView(), [{ type: 'text', seq: 1, text: 'Hola ' }, { type: 'text', seq: 2, text: 'Ana.' }])
    expect(v.items).toEqual([{ kind: 'text', role: 'fex', text: 'Hola Ana.' }])
  })

  it('keeps the real agent stream in order: intro text, claim cards, closing text (shared fixture)', () => {
    const v = run(newView(), events)
    expect(v.items.map((i) => i.kind)).toEqual(['text', 'claim', 'claim', 'text'])
    expect(v.items[0]).toMatchObject({ role: 'fex', text: 'Esto es lo que encontré. Cada punto muestra de dónde viene.' })
    expect(v.items[1]).toMatchObject({ section: 'insights' })
    expect(v.items[2]).toMatchObject({ section: 'peer_examples' })
    expect(v).toMatchObject({ step: 'consent', language: 'es', evidence: 'full', allowed: ['reopen_playback', 'set_consent', 'end'] })
  })

  it("starts a new FEX bubble after the producer speaks, and records the producer's words", () => {
    const v = run(newView(), [{ type: 'text', seq: 1, text: 'Pregunta 1' }])
    said(v, 'Respuesta')
    run(v, [{ type: 'text', seq: 1, text: 'Pregunta 2' }])
    expect(v.items.map((i) => i.kind === 'text' && `${i.role}:${i.text}`)).toEqual(['fex:Pregunta 1', 'producer:Respuesta', 'fex:Pregunta 2'])
  })

  it('starts a new FEX bubble for a turn started by a button (e.g. confirm after the playback)', () => {
    const v = run(newView(), [{ type: 'text', seq: 1, text: 'Esto es lo que entendí.' }, { type: 'done', seq: 2 }])
    beginTurn(v)
    run(v, [{ type: 'text', seq: 1, text: 'Esto es lo que encontré.' }])
    expect(v.items).toEqual([
      { kind: 'text', role: 'fex', text: 'Esto es lo que entendí.' },
      { kind: 'text', role: 'fex', text: 'Esto es lo que encontré.' },
    ])
  })

  it('starts a new FEX bubble even if the previous stream ended without done', () => {
    const v = run(newView(), [{ type: 'text', seq: 1, text: 'A' }])
    beginTurn(v)
    run(v, [{ type: 'text', seq: 1, text: 'B' }])
    expect(v.items.map((i) => i.kind === 'text' && i.text)).toEqual(['A', 'B'])
  })

  it('takes the conversation ID from the start stream', () => {
    expect(run(newView(), [{ type: 'conversation', conversationId: 'c-9' }]).conversationId).toBe('c-9')
  })

  it('is busy from the start of a turn until done, and clears the last error when a turn starts', () => {
    const v = run(newView(), [{ type: 'error', seq: 1, code: 'agent_failed', message: 'Algo falló' }])
    expect(v.error).toEqual({ code: 'agent_failed', message: 'Algo falló' })
    beginTurn(v)
    expect(v.busy).toBe(true)
    expect(v.error).toBeNull()
    run(v, [{ type: 'done', seq: 1 }])
    expect(v.busy).toBe(false)
  })

  it('shows a mid-stream error as a notice in the transcript', () => {
    const v = run(newView(), [{ type: 'text', seq: 1, text: 'Esto es' }, { type: 'error', seq: 2, code: 'agent_failed', message: 'Puede intentarlo de nuevo.' }])
    expect(v.items.at(-1)).toEqual({ kind: 'notice', tone: 'error', text: 'Puede intentarlo de nuevo.' })
  })

  it('records a saved record, and shows it in the transcript', () => {
    const v = run(newView(), [{ type: 'record_saved', seq: 1, status: 'completed', consent_scope: 'internal', version: 1 }])
    expect(v.record).toEqual({ status: 'completed', consent_scope: 'internal', version: 1 })
    expect(v.items.at(-1)).toEqual({ kind: 'record', status: 'completed', consent_scope: 'internal', version: 1 })
  })

  it('tracks the current consent choice, and clears it when the description is reopened (agent clears it too)', () => {
    const v = run(newView(), [{ type: 'record_saved', seq: 1, status: 'completed', consent_scope: 'internal', version: 1 }])
    expect(v.consent).toBe('internal')
    run(v, [{ type: 'record_saved', seq: 1, status: 'declined', consent_scope: 'declined', version: 2 }])
    expect(v.consent).toBe('declined')
    run(v, [{ type: 'step', seq: 2, step: 'playback', language: 'es' }])
    expect(v.consent).toBeNull()
    expect(v.record?.version).toBe(2) // the saved-record history is kept
  })

  it('clears the shown feedback answer on a decline or a reopened description, as the agent does (#23)', () => {
    const v: LiveView = { ...newView(), feedback: 'yes' }
    run(v, [{ type: 'record_saved', seq: 1, status: 'declined', consent_scope: 'declined', version: 2 }])
    expect(v.feedback).toBeNull()
    v.feedback = 'no'
    run(v, [{ type: 'step', seq: 2, step: 'playback', language: 'es' }])
    expect(v.feedback).toBeNull()
  })

  it('rebuilds the view from a resume response: history, then the answer, step and allowed actions', () => {
    const v = fromResume('c-1', {
      step: 'consent', language: 'es', allowed: ['reopen_playback', 'set_consent', 'end'],
      answer: { insights: [claim('Lluvia')], peer_examples: [claim('Riego')], evidence: 'limited' },
      history: [
        { role: 'fex', text: '¿Qué ha sido lo más difícil?', at: '2026-11-04T10:00:00Z' },
        { role: 'producer', text: 'La lluvia', at: '2026-11-04T10:00:05Z' },
        { role: 'action', name: 'confirm_playback', args: {}, at: '2026-11-04T10:01:00Z' },
      ],
    })
    expect(v.conversationId).toBe('c-1')
    expect(v.items.map((i) => (i.kind === 'claim' ? `claim:${i.section}` : i.kind === 'text' ? i.role : i.kind)))
      .toEqual(['fex', 'producer', 'claim:insights', 'claim:peer_examples'])
    expect(v).toMatchObject({ step: 'consent', language: 'es', evidence: 'limited', busy: false })
  })
})
