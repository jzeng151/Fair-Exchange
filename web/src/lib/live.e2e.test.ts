// Live mode (#116), end to end: the web app's OWN client and view code driving the REAL local chain
// (chat API + agent). Skipped unless FEX_E2E_API_URL is set; scripts/e2e/run_local.sh sets it (also in CI).
import { describe, expect, it } from 'vitest'
import { liveProducers } from '../data/liveProducers'
import { createLiveClient } from './liveClient'
import { apply, beginTurn, fromResume, newView, said } from './liveView'
import type { LiveClient, StreamEvent } from './liveClient'
import type { LiveView } from './liveView'

const api = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.FEX_E2E_API_URL
const SPANISH = ['La lluvia ha bajado mucho y la cosecha de café cayó este año.', 'Empezó hace dos temporadas.',
  'Es grave, perdimos casi la mitad.', 'Probamos con abono, pero no alcanzó.']

async function turn(view: LiveView, events: AsyncGenerator<StreamEvent>) {
  beginTurn(view)
  for await (const e of events) apply(view, e)
  expect(view.busy).toBe(false) // every stream ends with done
}
const fexSaid = (v: LiveView) => v.items.filter((i) => i.kind === 'text' && i.role === 'fex').length

describe.skipIf(!api)('live mode against the real local chain', () => {
  const client: LiveClient = createLiveClient({ baseUrl: api ?? '', producerId: liveProducers[0]!.id })
  const view = newView()

  it('runs a full Spanish conversation the way the live chat does', { timeout: 120_000 }, async () => {
    await turn(view, client.start())
    expect(view.conversationId).toBeTruthy()
    expect(view.step).toBe('intake')
    const id = view.conversationId!

    for (const text of SPANISH) {
      said(view, text)
      await turn(view, client.message(id, text))
    }
    expect(view.step).toBe('playback')
    expect(view.language).toBe('es')
    expect(view.allowed).toContain('confirm_playback')

    const before = fexSaid(view)
    await turn(view, client.action(id, 'confirm_playback'))
    expect(fexSaid(view)).toBeGreaterThan(before)
    const claims = view.items.filter((i) => i.kind === 'claim')
    expect(new Set(claims.map((c) => c.kind === 'claim' && c.section))).toEqual(new Set(['insights', 'peer_examples']))
    for (const c of claims) if (c.kind === 'claim') expect(c.claim.citation.source && c.claim.citation.standard_clause).toBeTruthy()
    expect(view.step).toBe('consent')
    expect(view.allowed).toContain('set_consent')

    await turn(view, client.action(id, 'set_consent', { scope: 'internal' }))
    expect(view.record).toMatchObject({ status: 'completed', consent_scope: 'internal', version: 1 })
    expect(view.step).toBe('feedback')

    await turn(view, client.action(id, 'set_feedback', { value: 'yes' }))
    expect(view.record?.version).toBe(2)

    // A reload: the resume view rebuilds the same conversation
    const resumed = fromResume(id, await client.resume(id))
    expect(resumed.step).toBe('feedback')
    expect(resumed.items.filter((i) => i.kind === 'claim').length).toBe(claims.length)

    await turn(view, client.action(id, 'end'))
    expect(view.step).toBe('closed')
    expect(view.allowed).toEqual([])
  })

  it('a second producer cannot open that conversation (404)', async () => {
    const other = createLiveClient({ baseUrl: api ?? '', producerId: liveProducers[1]!.id })
    await expect(other.resume(view.conversationId!)).rejects.toMatchObject({ status: 404 })
  })

  it.each(liveProducers.map((p) => [p.scenarioId, p.id]))('every producer in the live picker can start a conversation (%s)', async (_place, id) => {
    const v = newView()
    await turn(v, createLiveClient({ baseUrl: api ?? '', producerId: id }).start())
    expect(v.step).toBe('intake')
    expect(v.items.some((i) => i.kind === 'text' && i.role === 'fex')).toBe(true)
  })
})
