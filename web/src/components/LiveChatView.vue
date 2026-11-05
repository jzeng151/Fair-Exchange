<script setup lang="ts">
// Live mode (#116): the producer chat against the REAL chat API (routes and stream: #25 spec).
// Everything FEX says comes from the agent; this view only renders events and sends the producer's
// words and button choices. The scripted demo (ChatView.vue) is untouched and stays the default.
import { computed, nextTick, reactive, ref } from 'vue'
import FexMark from './FexMark.vue'
import { copyFor } from '../data/liveCopy'
import { languageName, liveProducers } from '../data/liveProducers'
import { createLiveClient, LiveError } from '../lib/liveClient'
import { apply, beginTurn, fromResume, newView, said } from '../lib/liveView'
import type { ActionName, LiveClient, StreamEvent } from '../lib/liveClient'
import type { Item, LiveView } from '../lib/liveView'

const props = defineProps<{ apiUrl: string; makeClient?: (producerId: string) => LiveClient }>()

const producerId = ref<string | null>(null)
const view = reactive<LiveView>(newView())
const input = ref('')
const correcting = ref(false)
const changingConsent = ref(false) // feedback step: the consent choice collapses to one line until 'Change'
const scroller = ref<HTMLElement | null>(null)
let client: LiveClient | null = null
// Bumped whenever the producer changes: a turn started for an earlier producer stops applying events
// and never saves its conversation ID under the new producer.
let session = 0
const resumeFailed = ref<string | null>(null) // saved conversation we could not reopen for a temporary reason

// The shared demo passcode (#11 stand-in): the deployed API requires it, the local one ignores it.
// Kept for this tab only, never in the build.
const PASSCODE_KEY = 'fex.live.passcode'
const passcode = ref(readPasscode())
function readPasscode(): string {
  try { return sessionStorage.getItem(PASSCODE_KEY) ?? '' } catch { return '' }
}
function savePasscode() {
  try { sessionStorage.setItem(PASSCODE_KEY, passcode.value.trim()) } catch { /* storage unavailable */ }
}

const t = computed(() => copyFor(view.language))
const can = (a: ActionName) => view.allowed.includes(a)
const closed = computed(() => view.step === 'closed')
const canType = computed(() => !!view.conversationId && !closed.value && !view.busy)
const producer = computed(() => liveProducers.find((p) => p.id === producerId.value))

// Remember the last conversation per producer in this tab, so a reload resumes it (per-viewer convenience only).
const KEY = (id: string) => `fex.live.${id}`
function remember(id: string, conversationId: string | null) {
  try { conversationId ? sessionStorage.setItem(KEY(id), conversationId) : sessionStorage.removeItem(KEY(id)) } catch { /* storage unavailable */ }
}
function recall(id: string): string | null {
  try { return sessionStorage.getItem(KEY(id)) } catch { return null }
}

function reset(next = newView()) { Object.assign(view, next) }
async function scrollDown() {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}

function errorText(err: unknown): string {
  if (err instanceof LiveError) {
    if (err.status === 0) return t.value.errors.unreachable
    if (err.status === 409) return closed.value ? t.value.closed : t.value.errors.busy
    if (err.status === 404) return t.value.errors.notFound
    if (err.status === 401 || err.status === 403) return t.value.errors.signIn
  }
  return t.value.errors.other
}

/** One turn: send, then render each event as it arrives. Errors become a notice in the transcript. */
async function turn(events: () => AsyncGenerator<StreamEvent>) {
  const mine = session
  const owner = producerId.value
  beginTurn(view)
  try {
    for await (const e of events()) {
      if (mine !== session) return // the producer changed: stop reading this stream
      apply(view, e)
      await scrollDown()
    }
  } catch (err) {
    if (mine !== session) return
    view.items.push({ kind: 'notice', tone: 'error', text: errorText(err) })
    if (err instanceof LiveError && err.status === 404 && owner) remember(owner, null)
  } finally {
    if (mine === session) {
      view.busy = false
      if (owner) remember(owner, view.conversationId)
      await scrollDown()
    }
  }
}

async function pick(id: string) {
  const mine = ++session
  producerId.value = id
  resumeFailed.value = null
  savePasscode()
  client = props.makeClient
    ? props.makeClient(id)
    : createLiveClient({ baseUrl: props.apiUrl, producerId: id, passcode: passcode.value.trim() })
  const saved = recall(id)
  if (saved) {
    try {
      const resumed = await client.resume(saved)
      if (mine !== session) return
      reset(fromResume(saved, resumed))
      if (!closed.value) return void scrollDown()
    } catch (err) {
      if (mine !== session) return
      if (!(err instanceof LiveError && err.status === 404)) {
        // Temporary failure: keep the saved conversation and let the producer try again.
        reset()
        resumeFailed.value = saved
        view.items.push({ kind: 'notice', tone: 'error', text: errorText(err) })
        return
      }
      remember(id, null) // the server says it is gone
    }
  }
  await startNew()
}

async function startNew() {
  if (!client) return
  resumeFailed.value = null
  reset()
  correcting.value = false
  await turn(() => client!.start())
}

async function send() {
  const text = input.value.trim()
  if (!text || !canType.value || !client || !view.conversationId) return
  input.value = ''
  correcting.value = false
  said(view, text)
  const id = view.conversationId
  await turn(() => client!.message(id, text))
}

async function act(action: ActionName, args: Record<string, unknown> = {}) {
  if (!client || !view.conversationId || view.busy) return
  if (action === 'end' && !window.confirm(t.value.endConfirm)) return
  const id = view.conversationId
  if (action === 'set_consent') changingConsent.value = false
  await turn(() => client!.action(id, action, args))
}
const currentConsent = computed(() => view.consent)

function back() {
  session++
  resumeFailed.value = null
  producerId.value = null
  client = null
  reset()
}

// Group headings: show "What the data shows" / "What others have tried" before the first card of each section.
function headingBefore(i: number): string | null {
  const item = view.items[i] as Item
  if (item.kind !== 'claim') return null
  const prev = view.items[i - 1]
  if (prev?.kind === 'claim' && prev.section === item.section) return null
  return item.section === 'insights' ? t.value.insights : t.value.peers
}
const consentChoices = ['internal', 'internal_and_outward', 'declined'] as const
const feedbackChoices = ['yes', 'somewhat', 'no'] as const
</script>

<template>
  <div class="chat-view live">
    <div v-if="!producerId" class="picker">
      <section class="intro-card">
        <FexMark :size="72" />
        <div>
          <h2>Live FEX</h2>
          <p>Every reply here comes from the real chat API and agent: sample producer data, cited sources and standards, and a saved record.</p>
          <p class="small">Chat API: <code>{{ apiUrl }}</code></p>
        </div>
      </section>
      <label class="passcode">
        <span>Demo passcode</span>
        <input v-model="passcode" type="password" autocomplete="off" data-field="passcode" />
        <span class="small">Ask the Fair Exchange team for it. Not needed for a local chat API.</span>
      </label>
      <h1>Choose a demo scenario</h1>
      <p class="small">Each card is an official demo scenario (<code>eval/scenarios/</code>): a sample producer and the messages to send.</p>
      <div class="picker-cards">
        <button v-for="p in liveProducers" :key="p.scenarioId" class="picker-card" :data-producer="p.id" :data-scenario="p.scenarioId" @click="pick(p.id)">
          <span class="flag" aria-hidden="true">{{ p.flag }}</span>
          <strong>{{ p.title }}</strong>
          <span class="label neutral">{{ languageName[p.language] ?? p.language }}</span>
          <span class="small">Scenario <code>{{ p.scenarioId }}</code></span>
        </button>
      </div>
    </div>

    <div v-else class="layout phone">
      <div class="chat-links">
        <button class="btn-text back-link" @click="back">← Choose another producer</button>
        <span class="small">{{ producer?.flag }} {{ producer?.title }}</span>
      </div>
      <section class="chat-panel" aria-label="Conversation">
        <div class="transcript" ref="scroller" aria-live="polite">
          <template v-for="(m, i) in view.items" :key="i">
            <h4 v-if="headingBefore(i)" class="claim-heading">{{ headingBefore(i) }}</h4>
            <div v-if="m.kind === 'text'" :class="['msg', m.role === 'fex' ? 'agent' : 'producer']">{{ m.text }}</div>
            <div v-else-if="m.kind === 'claim'" class="msg agent card claim" :data-section="m.section">
              <p>{{ m.claim.text }}</p>
              <p class="small cite">
                {{ t.source }}: {{ m.claim.citation.source }}<span v-if="m.claim.citation.period"> ({{ m.claim.citation.period }})</span>
                · {{ t.standard }}: {{ m.claim.citation.standard_clause }}
                <span v-if="m.claim.citation.strength"> · {{ t.strength[m.claim.citation.strength] }}</span>
              </p>
            </div>
            <div v-else-if="m.kind === 'notice'" class="alert warning" role="status">⚑ {{ m.text }}</div>
            <div v-else-if="m.kind === 'record'" class="alert info" role="status">
              ✓ {{ m.status === 'declined' ? t.declinedSaved : t.saved(m.version) }}
            </div>
          </template>
          <p v-if="view.evidence === 'limited' && !view.busy" class="small">{{ t.limited }}</p>
          <div v-if="view.busy" class="msg agent typing" :aria-label="t.working"><i></i><i></i><i></i></div>
          <div v-if="closed" class="alert" role="status">{{ t.closed }}</div>
        </div>

        <div v-if="resumeFailed" class="live-actions">
          <div class="btn-row">
            <button class="btn-primary" data-action="retry-resume" @click="pick(producerId!)">{{ t.retry }}</button>
            <button class="btn-text" @click="startNew">{{ t.start }}</button>
          </div>
        </div>
        <div v-if="!view.busy && view.conversationId" class="live-actions">
          <div v-if="view.step === 'playback'" class="btn-row">
            <button v-if="can('confirm_playback')" class="btn-primary" data-action="confirm_playback" @click="act('confirm_playback')">{{ t.confirm }}</button>
            <button v-if="can('correct_playback')" class="btn-default" data-action="correct_playback" @click="correcting = true">{{ t.correct }}</button>
          </div>
          <div v-if="can('retry_answer')" class="btn-row">
            <button class="btn-primary" data-action="retry_answer" @click="act('retry_answer')">{{ t.retry }}</button>
          </div>
          <div v-if="can('set_consent') && (view.step === 'consent' || changingConsent)" class="choice">
            <p>{{ t.consentAsk }}</p>
            <div class="btn-row">
              <button v-for="c in consentChoices" :key="c" class="btn-default" :data-consent="c"
                :aria-pressed="currentConsent === c" @click="act('set_consent', { scope: c })">{{ t.consent[c] }}</button>
            </div>
          </div>
          <p v-else-if="can('set_consent')" class="small consent-line">
            <template v-if="currentConsent">{{ t.yourChoice }}: {{ t.consent[currentConsent] }}</template>
            <template v-else>{{ t.consentAsk }}</template>
            <button class="btn-text inline" data-action="change-consent" @click="changingConsent = true">{{ t.change }}</button>
          </p>
          <div v-if="can('set_feedback')" class="choice">
            <p>{{ t.feedbackAsk }}</p>
            <div class="btn-row">
              <button v-for="f in feedbackChoices" :key="f" class="btn-default" :data-feedback="f" @click="act('set_feedback', { value: f })">{{ t.feedback[f] }}</button>
            </div>
          </div>
          <div class="btn-row secondary">
            <button v-if="can('reopen_playback')" class="btn-text" data-action="reopen_playback" @click="act('reopen_playback')">{{ t.reopen }}</button>
            <button v-if="can('end')" class="btn-text" data-action="end" @click="act('end')">
              {{ view.step === 'intake' || view.step === 'playback' || view.step === 'respond' ? t.stop : t.end }}
            </button>
            <button v-if="closed" class="btn-primary" @click="startNew">{{ t.start }}</button>
          </div>
        </div>

        <form class="composer" @submit.prevent="send">
          <label class="sr-only" for="live-msg">Message</label>
          <input id="live-msg" v-model="input" :placeholder="correcting ? t.correctPlaceholder : t.placeholder" :disabled="!canType" autocomplete="off" />
          <button class="btn-primary" :disabled="!canType || !input.trim()">{{ t.send }}</button>
        </form>
      </section>
    </div>
  </div>
</template>

<style scoped>
.claim-heading { margin: 12px 0 4px; font-size: 0.95rem; }
.claim .cite { margin-top: 6px; font-size: 13px; }
.live-actions { display: flex; flex-direction: column; gap: 6px; padding: 6px 0 2px; border-top: 1px solid var(--ft-ui-border, #dadce0); }
.live-actions .btn-row { margin-top: 4px; gap: 6px; }
.live-actions .btn-default, .live-actions .btn-primary { min-height: 40px; padding: 6px 12px; font-size: 14px; }
.live-actions .btn-default[aria-pressed='true'] { background: var(--ft-ui-primary-tint); font-weight: 600; }
.live-actions .btn-row.secondary { margin-top: 0; }
.live-actions .btn-row.secondary .btn-text { min-height: 36px; padding: 4px 8px 4px 0; font-size: 14px; }
.choice p, .consent-line { margin: 0; }
.btn-text.inline { min-height: 0; padding: 0 4px; text-decoration: underline; }
code { overflow-wrap: anywhere; }
.passcode { display: flex; flex-direction: column; gap: 4px; max-width: 320px; margin: 12px 0; }
.passcode input { min-height: 40px; padding: 6px 10px; font-size: 15px; }
</style>
