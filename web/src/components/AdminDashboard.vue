<script setup lang="ts">
// Admin analytics dashboard (issue #33). Shows only what the analytics rules (#29) allow:
// aggregate counts of consented records, declines as a count, groups under 5 hidden,
// reviewed records by default. Demo mode: computed in the browser from this browser's records.
// Live mode (when the site is built with a chat API address): the deployed analytics API (#29), behind the
// admin passcode stand-in (#11). The server has already hidden small groups; live mode only displays them.
import { computed, ref, watch } from 'vue'
import { MIN_GROUP, summarize } from '../lib/analytics'
import { dashboardRecords } from '../lib/dashboardSeed'
import { loadRecords, saveRecord } from '../lib/demoStore'
import { LiveError } from '../lib/liveClient'
import { cellCount, fetchAnalytics, toBreakdown, type AnalyticsResponse, type AnalyticsSection } from '../lib/liveAnalytics'
import BarBreakdown from './BarBreakdown.vue'

const props = defineProps<{ apiUrl?: string }>()
const source = ref<'demo' | 'live'>('demo')

const records = ref(loadRecords())
const includePending = ref(false)
const asTable = ref(false)
const s = computed(() => summarize(records.value, { includePending: includePending.value }))
const hasSample = computed(() => records.value.some((r) => r.record_id.startsWith('SEED-')))

function refresh() { records.value = loadRecords() }
defineExpose({ refresh })

function loadSample() {
  for (const r of dashboardRecords(new Date()).reverse()) saveRecord(r)
  refresh()
}
const LANGUAGES: Record<string, string> = { es: 'Spanish', en: 'English', fr: 'French', pt: 'Portuguese' }
const show = (k: number | null) => (k === null ? 'hidden' : String(k))

// Live mode. The admin passcode is kept for this tab only, never in the build.
const ADMIN_KEY = 'fex.admin.passcode'
const adminPasscode = ref((() => { try { return sessionStorage.getItem(ADMIN_KEY) ?? '' } catch { return '' } })())
const live = ref<AnalyticsResponse | null>(null)
const liveError = ref<string | null>(null)
const loading = ref(false)
async function loadLive() {
  if (!props.apiUrl) return
  try { sessionStorage.setItem(ADMIN_KEY, adminPasscode.value.trim()) } catch { /* storage unavailable */ }
  loading.value = true
  liveError.value = null
  try {
    live.value = await fetchAnalytics(props.apiUrl, adminPasscode.value.trim(), includePending.value)
  } catch (err) {
    live.value = null
    const status = err instanceof LiveError ? err.status : -1
    liveError.value = status === 401 || status === 403 ? 'The admin passcode wasn’t accepted.'
      : status === 503 ? 'Analytics are temporarily unavailable. Please try again in a moment.'
        : status === 0 ? 'Can’t reach the analytics API right now.' : 'Something went wrong. Please try again.'
  } finally {
    loading.value = false
  }
}
watch(includePending, () => { if (source.value === 'live' && live.value) void loadLive() })
const sections = computed(() => live.value
  ? ([['Live records', live.value.live], ['Seeded demo data', live.value.seeded]] as [string, AnalyticsSection][])
  : [])
</script>

<template>
  <div class="dash">
    <div class="dash-head">
      <h1>Admin dashboard</h1>
      <p class="small">What producers are raising, in aggregate. Only counts are shown: no names, IDs or summaries.</p>
    </div>

    <div v-if="apiUrl" class="btn-group source" role="group" aria-label="Data source">
      <button :class="{ active: source === 'demo' }" :aria-pressed="source === 'demo'" @click="source = 'demo'">Demo data (this browser)</button>
      <button :class="{ active: source === 'live' }" :aria-pressed="source === 'live'" @click="source = 'live'">Live analytics API</button>
    </div>

    <div class="controls" role="group" aria-label="Dashboard options">
      <div class="btn-group" role="group" aria-label="Which records">
        <button :class="{ active: !includePending }" :aria-pressed="!includePending" @click="includePending = false">Reviewed only</button>
        <button :class="{ active: includePending }" :aria-pressed="includePending" @click="includePending = true">Include pending</button>
      </div>
      <div class="btn-group" role="group" aria-label="View">
        <button :class="{ active: !asTable }" :aria-pressed="!asTable" @click="asTable = false">Chart</button>
        <button :class="{ active: asTable }" :aria-pressed="asTable" @click="asTable = true">Table</button>
      </div>
      <button v-if="source === 'demo' && !hasSample" class="btn-text" @click="loadSample">Load sample data (60 synthetic records)</button>
    </div>

    <template v-if="source === 'live'">
      <form class="admin-pass" @submit.prevent="loadLive">
        <label>
          <span>Admin passcode</span>
          <input v-model="adminPasscode" type="password" autocomplete="off" data-field="admin-passcode" />
        </label>
        <button class="btn-primary" :disabled="loading || !adminPasscode.trim()">{{ loading ? 'Loading…' : 'Load analytics' }}</button>
      </form>
      <p v-if="liveError" class="alert warning" role="status">{{ liveError }}</p>
      <section v-for="[heading, sec] in sections" :key="heading" class="live-section" :aria-label="heading">
        <h2>{{ heading }}</h2>
        <p v-if="heading !== 'Live records'" class="small">Synthetic records for the demo, never combined with live ones and not hidden for privacy.</p>
        <div class="tiles">
          <div class="panel tile"><span class="tile-num">{{ show(cellCount(sec.completed)) }}</span><span class="tile-label">saved with consent{{ includePending ? '' : ' (reviewed)' }}</span></div>
          <div class="panel tile"><span class="tile-num">{{ show(cellCount(sec.declined)) }}</span><span class="tile-label">declined to save (count only)</span></div>
        </div>
        <div class="grid">
          <BarBreakdown title="Challenges raised" note="A record can have more than one challenge." :breakdown="toBreakdown(sec.by_tag)" :total="null" :as-table="asTable" />
          <BarBreakdown title="Language" :labels="LANGUAGES" :breakdown="toBreakdown(sec.by_language)" :total="null" :as-table="asTable" />
          <BarBreakdown title="Type of organization" :breakdown="toBreakdown(sec.by_entity_type)" :total="null" :as-table="asTable" />
          <BarBreakdown title="Was the conversation helpful?" :breakdown="toBreakdown(sec.by_feedback)" :total="null" :as-table="asTable" />
          <BarBreakdown title="Consent given" :breakdown="toBreakdown(sec.by_consent_scope)" :total="null" :as-table="asTable" />
          <BarBreakdown title="Evidence found" :breakdown="toBreakdown(sec.by_evidence)" :total="null" :as-table="asTable" />
        </div>
        <section class="panel footprint" aria-label="AI footprint">
          <h3>AI footprint (total tokens per model)</h3>
          <table class="bd-table">
            <thead><tr><th scope="col">Model</th><th scope="col">Input tokens</th><th scope="col">Output tokens</th></tr></thead>
            <tbody>
              <tr v-for="f in sec.ai_footprint" :key="f.model_id"><td>{{ f.model_id }}</td><td>{{ f.input_tokens }}</td><td>{{ f.output_tokens }}</td></tr>
              <tr v-if="!sec.ai_footprint.length"><td colspan="3" class="small">No model use recorded.</td></tr>
            </tbody>
          </table>
        </section>
      </section>
    </template>

    <template v-else>

    <div class="tiles">
      <div class="panel tile"><span class="tile-num">{{ show(s.included) }}</span><span class="tile-label">records in view{{ includePending ? '' : ' (reviewed)' }}</span></div>
      <div class="panel tile"><span class="tile-num">{{ show(s.declined) }}</span><span class="tile-label">producers declined to save (count only)</span></div>
      <div v-if="!includePending" class="panel tile"><span class="tile-num">{{ show(s.pendingNotShown) }}</span><span class="tile-label">waiting for review, not shown</span></div>
    </div>

    <p v-if="s.included === null" class="alert info">
      Fewer than {{ MIN_GROUP }} records are in view, so every number is hidden to protect producers.
      {{ hasSample ? 'Try “Include pending”.' : 'Load sample data to see the dashboard working.' }}
    </p>

    <div class="grid">
      <BarBreakdown title="Challenges raised" note="A record can have more than one challenge, so shares add up to more than 100%."
                    :breakdown="s.byTag" :total="s.included" :as-table="asTable" />
      <BarBreakdown title="Language" :labels="LANGUAGES" :breakdown="s.byLanguage" :total="s.included" :as-table="asTable" />
      <BarBreakdown title="Type of organization" :breakdown="s.byEntity" :total="s.included" :as-table="asTable" />
      <BarBreakdown title="Was the conversation helpful?" :breakdown="s.byFeedback" :total="s.included" :as-table="asTable" />
    </div>

    </template>

    <p class="small rules">
      Rules: only records producers agreed to save · declines are a count only · any group under {{ MIN_GROUP }} is hidden,
      plus one more where the hidden number could otherwise be worked out · reviewed records by default.
    </p>
  </div>
</template>

<style scoped>
.dash-head h1 { font-family: var(--ft-font-brand-heading); color: var(--ft-brand-indigo); font-size: 26px; margin: 0 0 2px; }
.controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0; }
.controls .btn-group { flex-wrap: wrap; }
.controls .btn-group button { white-space: nowrap; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 12px; }
.tile { display: grid; gap: 2px; padding: 14px 16px; }
.tile-num { font-size: 32px; font-weight: 600; color: var(--ft-ui-text, #343637); font-variant-numeric: tabular-nums; line-height: 1.1; }
.tile-label { font-size: 14px; color: var(--ft-ui-text-secondary, #5f6368); }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.grid > * { min-width: 0; }
.rules { margin-top: 12px; }
.source { margin: 8px 0; }
.admin-pass { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin: 8px 0 12px; }
.admin-pass label { display: flex; flex-direction: column; gap: 4px; }
.admin-pass input { min-height: 40px; padding: 6px 10px; font-size: 15px; }
.live-section h2 { font-size: 20px; margin: 16px 0 8px; }
.footprint { margin-top: 12px; }
.bd-table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px; }
.bd-table th, .bd-table td { text-align: left; padding: 6px 4px; border-bottom: 1px solid var(--ft-ui-border, #e2e5e8); }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style>
