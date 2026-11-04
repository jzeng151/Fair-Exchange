<script setup lang="ts">
import { ref, reactive, computed, nextTick } from 'vue'
import { scenarios as producers } from '../data/scenarios'
import { t as T, detect } from '../data/i18n'
import { buildCompletedRecord, buildDeclinedRecord } from '../lib/record'
import { saveRecord as storeRecord, setFeedback } from '../lib/demoStore'
import AnswerCards from './AnswerCards.vue'
import FexMark from './FexMark.vue'
import AboutAI from './AboutAI.vue'
import { newUsage, addCall, tokensFromText, summarize } from '../data/energy'
import RetrievalChecklist from './RetrievalChecklist.vue'

import type { Copy, Lang } from '../data/i18n'
import type { Scenario } from '../data/scenarios'

const props = withDefaults(defineProps<{ producerView?: boolean; subtitles?: boolean }>(), { producerView: false, subtitles: true })

type Field = 'challenge' | 'timing' | 'severity' | 'tried'
type Question = 'open' | 'timing' | 'severity' | 'tried'
type Model = 'small' | 'large' | 'none'
type Feedback = 'yes' | 'some' | 'no'
interface Msg {
  id: number
  role: 'agent' | 'producer' | 'system'
  kind: 'text' | 'notice' | 'loading' | 'checklist' | 'playback' | 'answer' | 'consent' | 'feedback' | 'energy'
  text?: string; en?: string; tone?: string; model?: Model
  voice?: boolean; dur?: number; warm?: boolean
  steps?: { active: boolean; done: boolean }[]
  level?: 'veryLow' | 'low' | 'moderate'
}
type NewMsg = Omit<Msg, 'id'>

const FIELDS: Field[] = ['challenge', 'timing', 'severity', 'tried']
const FEEDBACK: Feedback[] = ['yes', 'some', 'no']
const first = producers[0] as Scenario
const producerId = ref(first.id)
const producer = computed<Scenario>(() => producers.find((p) => p.id === producerId.value) ?? first)
const lang = computed<Lang>(() => producer.value.language)
const t = computed<Copy>(() => T[lang.value])
const EN: Copy = T.en
// English subtitles for presenters: team view + Spanish conversation only
const sub = computed(() => props.subtitles && lang.value === 'es')

const QUESTION_STAGES: Question[] = ['open', 'timing', 'severity', 'tried']
const ASK = { timing: 'askTiming', severity: 'askSeverity', tried: 'askTried' } as const
const isQuestion = (s: string): s is Question => (QUESTION_STAGES as string[]).includes(s)

const started = ref(false)
const stage = ref<string>('open')
const messages = ref<Msg[]>([])
const input = ref('')
const answers = reactive<Partial<Record<Question, string>>>({})
const answersEn = reactive<Partial<Record<Question, string | null>>>({})
const playback = reactive({ challenge: '', timing: '', severity: '', tried: '', entity: '' })
const savedSummary = reactive({ challenge: '', timing: '', severity: '', tried: '', entity: '' })
const pii = reactive<{ flag: boolean; reasons: string[] }>({ flag: false, reasons: [] })
const log = ref<{ time: string; tool: string; detail: string }[]>([])
const recordId = ref<string | null>(null)
const oosCount = ref(0)      // out-of-scope requests this conversation
const blockedCount = ref(0)  // blocked cross-producer requests this conversation
const scroller = ref<HTMLElement | null>(null)
const typing = ref(false)      // agent 'typing…' dots
const recording = ref(false)   // simulated voice input
const selectedPeer = ref<number | null>(null) // map pin ↔ peer card
const editingSave = ref(false)  // save step: show the editable fields only when asked
const showAbout = ref(false)    // 'How FEX uses AI' explainer
let usage = newUsage()           // AI usage this conversation (estimated in the prototype)

const newRecordId = () => 'R-' + Date.now().toString(36).toUpperCase()
function now() { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
function addLog(tool: string, detail: string) { log.value.push({ time: now(), tool, detail }) }

// Spec 10: don't yank the view down while someone is reading earlier messages.
// Auto-scroll only if already near the bottom, or when the producer just sent something.
function nearBottom() { const el = scroller.value; return !el || el.scrollHeight - el.scrollTop - el.clientHeight < 140 }
async function push(msg: NewMsg) {
  const stick = msg.role === 'producer' || nearBottom()
  messages.value.push({ id: messages.value.length, ...msg })
  await nextTick()
  if (stick && scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
async function scrollDown() { const stick = nearBottom(); await nextTick(); if (stick && scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight }
// Agent messages show typing dots first, like a person replying
let session = 0 // bumps on reset so late messages from an old conversation are dropped
function trackUsage(msg: NewMsg) {
  const model = msg.model ?? (msg.role === 'agent' ? 'small' : 'none')
  if (model === 'none') return
  const context = 600 + tokensFromText(messages.value.map((m) => m.text || '').join(' ')) // instructions + conversation so far
  if (model === 'large') {
    const p = producer.value
    const L = lang.value
    const out = tokensFromText([p.summary[L] ?? '', ...p.insights.map((i) => i.text[L] ?? ''), ...p.peers.map((x) => x.text[L] ?? '')].join(' '))
    addCall(usage, 'large', context + 2500, out) // + tool results (records, data, peers, standards)
  } else {
    addCall(usage, 'small', context, tokensFromText(msg.text || '') + (msg.kind === 'playback' ? 150 : 0))
  }
}
async function say(msg: NewMsg) {
  trackUsage(msg)
  const mine = session
  typing.value = true
  await scrollDown()
  await sleep(msg.kind === 'text' ? 700 : 500)
  if (mine !== session) return
  typing.value = false
  await push(msg)
}

function reset() {
  session++
  usage = newUsage()
  showAbout.value = false
  stage.value = 'open'
  messages.value = []
  log.value = []
  recordId.value = null
  pii.flag = false; pii.reasons = []
  oosCount.value = 0; blockedCount.value = 0
  typing.value = false; recording.value = false; selectedPeer.value = null; editingSave.value = false
  for (const k of QUESTION_STAGES) { delete answers[k]; delete answersEn[k] }
  Object.assign(playback, { challenge: '', timing: '', severity: '', tried: '', entity: producer.value.entityType })
  addLog('session.start', `Session bound to producer ${producer.value.id} (${producer.value.region}). Tools read producer ID from session only.`)
  say({ role: 'agent', kind: 'text', text: t.value.greet, en: EN.greet, model: 'none' })
}

function start(id: string) { producerId.value = id; reset(); started.value = true }
function backToPicker() { started.value = false }
const FLAGS: Record<string, string> = { 'P-001': '🇨🇴', 'P-002': '🇲🇽', 'P-003': '🇨🇮' }

// Simulated voice input: 'records' for a moment, then sends the suggested answer as a voice note
async function speak() {
  if (!chips.value.length || recording.value) return
  const c = chips.value[0]
  if (!c) return
  recording.value = true
  await scrollDown()
  await sleep(1800)
  recording.value = false
  await send(c[lang.value] ?? c.en, c.en, { voice: true, dur: 4 + Math.floor(Math.random() * 6) })
}

const chips = computed(() => (isQuestion(stage.value) ? producer.value.chips[stage.value] : []))
const canType = computed(() => !['retrieving', 'done', 'declined'].includes(stage.value))

async function send(raw?: string, enText?: string, opts: { voice?: boolean; dur?: number } = {}) {
  const text = (raw ?? input.value).trim()
  if (!text || !canType.value) return
  input.value = ''
  await push({ role: 'producer', kind: 'text', text, en: enText, voice: opts.voice, dur: opts.dur })

  if (detect.pii(text)) {
    pii.flag = true
    pii.reasons.push(`Possible personal info in: “${text.slice(0, 60)}”` + (lang.value === 'es' && enText ? ` (EN: “${enText.slice(0, 60)}”)` : ''))
    addLog('comprehend.detectPii (simulated)', 'PII-like content found → record flagged for human review. No redaction.')
    await push({ role: 'system', kind: 'notice', tone: 'warning', text: t.value.pii, en: EN.pii })
  }
  if (detect.otherProducer(text, producer.value.id)) {
    blockedCount.value++
    addLog('get_producer_record', `REFUSED: request for another producer ID ignored; session producer is ${producer.value.id}.`)
    await say({ role: 'agent', kind: 'text', text: t.value.scope(producer.value.id), en: EN.scope(producer.value.id) })
    return
  }
  if (detect.decline(text)) return decline()
  if (detect.outOfScope(text)) {
    oosCount.value++
    addLog('scope.check', 'Out-of-scope request (certification status / complaint). Declined; nothing recorded.')
    await say({ role: 'agent', kind: 'text', text: t.value.outOfScope, en: EN.outOfScope })
    return
  }

  const current = stage.value
  if (isQuestion(current)) {
    answers[current] = text
    answersEn[current] = lang.value === 'en' ? text : enText || null
    const next = QUESTION_STAGES[QUESTION_STAGES.indexOf(current) + 1]
    await sleep(400)
    if (next && next !== 'open') {
      stage.value = next
      await say({ role: 'agent', kind: 'text', text: t.value[ASK[next]], en: EN[ASK[next]] })
    } else {
      Object.assign(playback, { challenge: answers.open ?? '', timing: answers.timing ?? '', severity: answers.severity ?? '', tried: answers.tried ?? '', entity: producer.value.entityType })
      stage.value = 'playback'
      addLog('agent.playback', 'Playing back understanding. No tools called until producer confirms.')
      await say({ role: 'agent', kind: 'playback' })
    }
  }
}

async function confirmPlayback() {
  if (stage.value !== 'playback') return
  Object.assign(savedSummary, playback)
  stage.value = 'retrieving'
  await push({ role: 'producer', kind: 'text', text: t.value.confirm, en: EN.confirm })
  const p = producer.value
  const tools: [string, string][] = [
    ['get_producer_record', `producer_id=${p.id} (from session) → ${p.premiumProjects.length} Premium projects, 1 survey`],
    ['get_regional_context', `region=${p.region}, crop=${p.crop} (from session) → ${p.insights.filter(i => !i.source.startsWith('Your')).length} dataset matches`],
    ['find_peer_examples', `tags=[${p.tags.join(', ')}], crop=${p.crop}, entity=${playback.entity} → ${p.peers.length} peers`],
    ['check_standards', `Matched each claim to a real APS/FPS clause (demo mapping)`],
  ]
  await push({ role: 'system', kind: 'checklist', steps: tools.map(() => ({ active: false, done: false })) })
  const steps = messages.value[messages.value.length - 1]?.steps ?? []
  for (const [i, [tool, detail]] of tools.entries()) {
    const step = steps[i]
    if (step) step.active = true
    await sleep(750)
    addLog(tool, detail)
    if (step) { step.active = false; step.done = true }
  }
  await sleep(300)
  await say({ role: 'agent', kind: 'answer', model: 'large' })
  stage.value = 'reading' // producer taps through the cards, then continues to the save step
}

const FIELD_TO_ANSWER: Record<Field, Question> = { challenge: 'open', timing: 'timing', severity: 'severity', tried: 'tried' }
// English for an editable field: the known translation if unchanged, otherwise a clear note
function enFor(obj: Record<Field, string>, f: Field): string {
  const a = FIELD_TO_ANSWER[f]
  const english = answersEn[a]
  if (obj[f] === answers[a] && english) return english
  return '(Edited or typed text: no English translation in this prototype)'
}

function englishSummary(): Record<Field | 'entity', string> {
  if (lang.value === 'en') return { ...savedSummary }
  const out = { entity: savedSummary.entity } as Record<Field | 'entity', string>
  for (const f of FIELDS) {
    const a = FIELD_TO_ANSWER[f]
    const english = answersEn[a]
    out[f] = savedSummary[f] === answers[a] && english ? english : '[Translation pending human review — simulated]'
  }
  return out
}

async function finishReading() {
  if (stage.value !== 'reading') return
  stage.value = 'consent'
  await say({ role: 'agent', kind: 'consent', model: 'none' })
}

async function saveRecord() {
  if (stage.value !== 'consent') return
  await push({ role: 'producer', kind: 'text', text: t.value.save, en: EN.save })
  const p = producer.value
  addCall(usage, 'small', 600 + tokensFromText(messages.value.map((m) => m.text || '').join(' ')), 40) // challenge tagging
  const L = lang.value
  const asClaim = (c: { text: { en: string; es?: string }; source: string; clause: string; strength: 'exact' | 'nearest' | 'limited'; period?: string }) => ({
    text: c.text[L] ?? c.text.en,
    citation: { source: c.source, standard_clause: c.clause, strength: c.strength, period: c.period ?? null },
  })
  const rec = buildCompletedRecord({
    recordId: newRecordId(), producerId: p.id, now: new Date(), language: L, entityType: savedSummary.entity,
    summaryOriginal: savedSummary.challenge, summaryEnglish: englishSummary().challenge, tags: p.tags,
    insights: p.insights.map(asClaim),
    peerExamples: p.peers.map((x) => asClaim({ ...x, source: `${x.org} (${x.place})`, strength: 'nearest' })),
    feedback: null, piiFlag: pii.flag,
  })
  storeRecord(rec)
  recordId.value = rec.record_id
  addLog('write_back_record', `Record ${rec.record_id} saved (demo mode): source="agent conversation", review_status=pending${pii.flag ? ', pii_flag=true' : ''}`)
  await say({ role: 'agent', kind: 'text', text: t.value.saved, en: EN.saved, model: 'none' })
  stage.value = 'feedback'
  await say({ role: 'agent', kind: 'feedback', model: 'none' })
}

async function giveFeedback(key: Feedback) {
  if (stage.value !== 'feedback') return
  await push({ role: 'producer', kind: 'text', text: t.value.fb[key], en: EN.fb[key] })
  if (recordId.value) setFeedback(recordId.value, ({ yes: 'yes', some: 'somewhat', no: 'no' } as const)[key])
  addLog('record.update', `Feedback "${key}" stored on ${recordId.value}`)
  stage.value = 'done'
  await say({ role: 'agent', kind: 'text', text: t.value.thanks, en: EN.thanks, model: 'none' })
  await say({ role: 'agent', kind: 'text', text: t.value.closing, en: EN.closing, warm: true, model: 'none' })
  await showEnergy()
}

async function showEnergy() {
  const u = summarize(usage)
  addLog('ai.usage', `small model: ${u.smallCalls} calls / ${u.smallTokens} tokens · large model: ${u.largeCalls} calls / ${u.largeTokens} tokens · ~${u.estWh} Wh (rough estimate)`)
  await push({ role: 'system', kind: 'energy', level: u.level })
}

async function decline() {
  if (stage.value === 'declined' || stage.value === 'done') return
  const rec = buildDeclinedRecord({ recordId: newRecordId(), producerId: producer.value.id, now: new Date() })
  storeRecord(rec)
  addLog('write_back_record', `Declined outcome ${rec.record_id}: producer ID + timestamp only. No narrative, no feedback.`)
  stage.value = 'declined'
  await say({ role: 'agent', kind: 'text', text: t.value.declined, en: EN.declined })
  await showEnergy()
}

function strengthClass(s: 'exact' | 'nearest' | 'limited') { return ({ exact: 'ok', nearest: 'mid', limited: 'low' } as const)[s] }
function takeawayText(L = lang.value) {
  const p = producer.value, tt = T[L]
  const challenge = L === lang.value ? savedSummary.challenge : englishSummary().challenge
  return [
    `${tt.takeaway.challenge}: ${challenge}`,
    `${tt.takeaway.data}:`, ...p.insights.map((i) => `• ${i.text[L]} (${i.source})`),
    `${tt.takeaway.others}:`, ...p.peers.map((x) => `• ${x.text[L]} (${x.org})`),
  ].join('\n')
}
const copied = ref(false)
async function copyTakeaway() {
  try { await navigator.clipboard.writeText(takeawayText()); copied.value = true; setTimeout(() => (copied.value = false), 1500) } catch { /* ignore */ }
}

</script>

<template>
  <!-- single root so the side switch (v-show) can hide this whole screen -->
  <div class="chat-view">
    <AboutAI v-if="showAbout && !started" :t="T.en" :en="EN" :sub="false" lang="en" @close="showAbout = false" />
    <div v-if="!started" class="picker">
      <section class="intro-card">
        <FexMark :size="72" />
        <div>
          <h2>Meet FEX</h2>
          <p>Fair Trade USA’s computer assistant for producers. FEX listens, shares data and what other groups have tried, and leaves every decision to you.</p>
          <button class="btn-text" @click="showAbout = true">ℹ️ How FEX uses AI</button>
        </div>
      </section>
      <h1>Choose a demo producer</h1>
      <p class="small">Each card is a synthetic producer. You will see exactly what that producer would see.</p>
      <div class="picker-cards">
        <button v-for="p in producers" :key="p.id" class="picker-card" @click="start(p.id)">
          <span class="flag" aria-hidden="true">{{ FLAGS[p.id] }}</span>
          <strong>{{ p.scenario }}</strong>
          <span>{{ p.region }}</span>
          <span class="small">{{ p.crop }} · {{ p.entityType }}</span>
          <span class="label neutral">{{ p.language === 'es' ? 'Español (with English subtitles)' : 'English' }}</span>
        </button>
      </div>
    </div>
    <div v-else :class="['layout', { phone: producerView }]">
      <div class="chat-links">
        <button class="btn-text back-link" @click="backToPicker">← Choose another producer</button>
        <button class="btn-text info-link" @click="showAbout = true" :title="EN.howAI">ℹ️ {{ t.howAI }}</button>
      </div>
      <AboutAI v-if="showAbout" :t="t" :en="EN" :sub="sub" :lang="lang" @close="showAbout = false" />
      <section class="chat-panel" aria-label="Conversation">

        <div class="transcript" ref="scroller" aria-live="polite">
          <template v-for="m in messages" :key="m.id">
            <div v-if="m.kind === 'text'" :class="['msg', m.role, { voice: m.voice, warm: m.warm }]"><span v-if="m.voice" class="voice-head">🎤 {{ t.voiceNote }}<span v-if="sub" class="sub-inline"> ({{ EN.voiceNote }})</span> · 0:0{{ m.dur }} <span class="wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span></span>{{ m.text }}<span v-if="sub && m.en" class="sub">{{ m.en }}</span><span v-else-if="sub && m.role === 'producer'" class="sub">(Typed text: no English translation in this prototype)</span></div>

            <div v-else-if="m.kind === 'energy'" class="energy-note" role="status">
              <span aria-hidden="true">🌱</span>
              <span>{{ t.energy[m.level ?? 'veryLow'] }}<span v-if="sub" class="sub">{{ EN.energy[m.level ?? 'veryLow'] }}</span></span>
              <button class="btn-text" @click="showAbout = true">{{ t.howAI }}</button>
            </div>

            <div v-else-if="m.kind === 'notice'" :class="['alert', m.tone]" role="status">⚑ {{ m.text }}<span v-if="sub && m.en" class="sub">{{ m.en }}</span><span v-else-if="sub && m.role === 'producer'" class="sub">(Typed text: no English translation in this prototype)</span></div>

            <div v-else-if="m.kind === 'loading'" class="loading">⏳ {{ m.text }}<span v-if="sub && m.en" class="sub">{{ m.en }}</span><span v-else-if="sub && m.role === 'producer'" class="sub">(Typed text: no English translation in this prototype)</span></div>

            <RetrievalChecklist v-else-if="m.kind === 'checklist'" :steps="m.steps ?? []" :lang="lang" :sub="sub" :en="EN" :t="t" />

            <div v-else-if="m.kind === 'playback'" class="msg agent card">
              <p>{{ t.playbackIntro }}<span v-if="sub" class="sub">{{ EN.playbackIntro }}</span></p>
              <div class="pb-grid">
                <label v-for="f in FIELDS" :key="f">
                  <span>{{ t.fields[f] }}<em v-if="sub" class="sub-inline"> ({{ EN.fields[f] }})</em></span>
                  <textarea v-model="playback[f]" rows="2" :disabled="stage !== 'playback'"></textarea>
                  <em v-if="sub" class="sub">{{ enFor(playback, f) }}</em>
                </label>
                <label>
                  <span>{{ t.fields.entity }}<em v-if="sub" class="sub-inline"> ({{ EN.fields.entity }})</em></span>
                  <select v-model="playback.entity" :disabled="stage !== 'playback'">
                    <option v-for="(label, val) in t.entities" :key="val" :value="val">{{ label }}{{ sub ? ' (' + EN.entities[val] + ')' : '' }}</option>
                  </select>
                </label>
              </div>
              <button v-if="stage === 'playback'" class="btn-primary" @click="confirmPlayback">{{ t.confirm }}</button><span v-if="sub && stage === 'playback'" class="sub">Button: “{{ EN.confirm }}”</span>
            </div>

            <div v-else-if="m.kind === 'answer'" class="msg agent card wide">
              <AnswerCards :producer="producer" :lang="lang" :sub="sub" :en="EN" :t="t"
                :challenge="savedSummary.challenge" :challenge-en="englishSummary().challenge"
                :takeaway-text="takeawayText()" :active="stage === 'reading'" @done="finishReading" />
            </div>

            <div v-else-if="m.kind === 'consent'" class="msg agent card">
              <p>{{ t.consentAsk }}<span v-if="sub" class="sub">{{ EN.consentAsk }}</span></p>
              <div class="save-preview">
                <p class="quote">“{{ savedSummary.challenge }}”</p>
                <p v-if="sub" class="sub">“{{ enFor(savedSummary, 'challenge') }}”</p>
                <button v-if="stage === 'consent'" class="btn-text" :aria-expanded="editingSave" @click="editingSave = !editingSave">
                  ✏️ {{ editingSave ? t.doneEditing : t.editSummary }}<span v-if="sub" class="sub-inline"> ({{ editingSave ? EN.doneEditing : EN.editSummary }})</span>
                </button>
                <div v-if="editingSave && stage === 'consent'" class="pb-grid">
                  <label v-for="f in FIELDS" :key="f">
                    <span>{{ t.fields[f] }}<em v-if="sub" class="sub-inline"> ({{ EN.fields[f] }})</em></span>
                    <textarea v-model="savedSummary[f]" rows="2"></textarea>
                    <em v-if="sub" class="sub">{{ enFor(savedSummary, f) }}</em>
                  </label>
                </div>
              </div>
              <p v-if="!producerView" class="small">Tags: {{ producer.tags.join(', ') }} · source = “agent conversation” · review status: pending<span v-if="pii.flag"> · ⚑ PII flag</span></p>
              <div v-if="stage === 'consent'" class="btn-row">
                <button class="btn-default" @click="saveRecord">{{ t.save }}</button>
                <button class="btn-default" @click="decline">{{ t.dontSave }}</button>
                <span v-if="sub" class="sub-inline">({{ EN.save }} / {{ EN.dontSave }})</span>
              </div>
            </div>

            <div v-else-if="m.kind === 'feedback'" class="msg agent card">
              <p>{{ t.feedbackAsk }}<span v-if="sub" class="sub">{{ EN.feedbackAsk }}</span></p>
              <div v-if="stage === 'feedback'" class="btn-row">
                <button class="btn-default" v-for="k in FEEDBACK" :key="k" @click="giveFeedback(k)">{{ t.fb[k] }}</button>
                <span v-if="sub" class="sub-inline">({{ EN.fb.yes }} / {{ EN.fb.some }} / {{ EN.fb.no }})</span>
              </div>
            </div>
          </template>
          <div v-if="typing" class="msg agent typing" aria-label="typing"><i></i><i></i><i></i></div>
          <div v-if="recording" class="recording" role="status">
            <span class="rec-dot" aria-hidden="true"></span> {{ t.listening }}<span v-if="sub" class="sub-inline"> ({{ EN.listening }})</span>
            <span class="wave big" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span>
          </div>
        </div>

        <div v-if="chips.length" class="chips" aria-label="Suggested replies">
          <span v-if="!producerView" class="small">Suggested reply:</span>
          <button v-for="(c, n) in chips" :key="n" class="chip" @click="send(c[lang], c.en)">{{ c[lang] }}<span v-if="sub" class="sub">{{ c.en }}</span></button>
        </div>
        <form class="composer" @submit.prevent="send()">
          <label class="sr-only" for="msg">Message</label>
          <button type="button" class="mic" :class="{ rec: recording }" :disabled="!chips.length || recording" :title="t.voiceSim" :aria-label="t.tapToSpeak" @click="speak">🎤</button>
          <input id="msg" v-model="input" :placeholder="sub ? 'Mensaje / Message…' : t.placeholder" :disabled="!canType" autocomplete="off" />
          <button class="btn-primary" :disabled="!canType || !input.trim()">{{ t.send }}<span v-if="sub"> / {{ EN.send }}</span></button>
        </form>
      </section>
    </div>
  </div>
</template>
