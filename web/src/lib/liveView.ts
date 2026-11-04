// Live mode (#116): what the live chat shows, built from the chat API's events. Pure, so it is tested
// without a browser or a server. The component keeps one view in a Vue `reactive` and calls these.
import type { Claim } from '../../../api/src/types/conversation-record'
import type { ActionName, Event, ResumeResponse, StreamEvent } from './liveClient'

type Step = ResumeResponse['step']
type RecordSaved = Extract<Event, { type: 'record_saved' }>

export type Item =
  | { kind: 'text'; role: 'fex' | 'producer'; text: string }
  | { kind: 'claim'; section: 'insights' | 'peer_examples'; claim: Claim }
  | { kind: 'notice'; tone: 'error'; text: string }
  | { kind: 'record'; status: RecordSaved['status']; consent_scope: RecordSaved['consent_scope']; version: number }

export interface LiveView {
  conversationId: string | null
  step: Step | null
  language: string
  allowed: ActionName[]
  items: Item[]
  evidence: 'full' | 'limited' | null
  record: { status: RecordSaved['status']; consent_scope: RecordSaved['consent_scope']; version: number } | null
  /** The consent choice in force now. Null until chosen, and again after the description is reopened
   *  (the agent clears consent and feedback then, without a record_saved event). Unknown after a resume. */
  consent: 'internal' | 'internal_and_outward' | 'declined' | null
  error: { code: string; message: string } | null
  busy: boolean
  /** Streamed text joins the last FEX bubble only while this is true. */
  open: boolean
}

export function newView(): LiveView {
  return { conversationId: null, step: null, language: 'en', allowed: [], items: [], evidence: null, record: null, consent: null, error: null, busy: false, open: false }
}

/** A request is about to be sent: new FEX text goes in a new bubble. */
export function beginTurn(view: LiveView): void {
  view.busy = true
  view.error = null
  view.open = false
}

/** The producer's own words, shown as sent. */
export function said(view: LiveView, text: string): void {
  view.items.push({ kind: 'text', role: 'producer', text })
  view.open = false
}

export function apply(view: LiveView, event: StreamEvent): void {
  switch (event.type) {
    case 'conversation':
      view.conversationId = event.conversationId
      return
    case 'text': {
      const last = view.items.at(-1)
      if (view.open && last?.kind === 'text' && last.role === 'fex') last.text += event.text
      else view.items.push({ kind: 'text', role: 'fex', text: event.text })
      view.open = true
      return
    }
    case 'claim':
      view.items.push({ kind: 'claim', section: event.section, claim: event.claim })
      view.open = false
      return
    case 'answer':
      view.evidence = event.evidence
      return
    case 'step':
      view.step = event.step
      view.language = event.language
      if (event.step === 'intake' || event.step === 'playback') view.consent = null
      return
    case 'actions':
      view.allowed = event.allowed
      view.language = event.language
      return
    case 'record_saved': {
      const record = { status: event.status, consent_scope: event.consent_scope, version: event.version }
      view.record = record
      view.consent = event.status === 'declined' ? 'declined' : event.consent_scope
      view.items.push({ kind: 'record', ...record })
      view.open = false
      return
    }
    case 'error':
      view.error = { code: event.code, message: event.message }
      view.items.push({ kind: 'notice', tone: 'error', text: event.message })
      view.open = false
      return
    case 'done':
      view.busy = false
      view.open = false
      return
  }
}

/** The view for a conversation opened again later (GET /conversations/{id}). */
export function fromResume(conversationId: string, r: ResumeResponse): LiveView {
  const view = newView()
  view.conversationId = conversationId
  view.step = r.step
  view.language = r.language
  view.allowed = r.allowed
  for (const h of r.history) if (h.role !== 'action') view.items.push({ kind: 'text', role: h.role, text: h.text })
  if (r.answer) {
    for (const claim of r.answer.insights) view.items.push({ kind: 'claim', section: 'insights', claim })
    for (const claim of r.answer.peer_examples) view.items.push({ kind: 'claim', section: 'peer_examples', claim })
    view.evidence = r.answer.evidence
  }
  return view
}
