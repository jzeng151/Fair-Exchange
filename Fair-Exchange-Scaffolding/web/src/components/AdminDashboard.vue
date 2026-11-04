<script setup lang="ts">
// Admin analytics dashboard (issue #33). Shows only what the analytics rules (#29) allow:
// aggregate counts of consented records, declines as a count, groups under 5 hidden,
// reviewed records by default. Demo mode: computed in the browser until the analytics API exists.
import { computed, ref } from 'vue'
import { MIN_GROUP, summarize } from '../lib/analytics'
import { dashboardRecords } from '../lib/dashboardSeed'
import { loadRecords, saveRecord } from '../lib/demoStore'
import BarBreakdown from './BarBreakdown.vue'

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
</script>

<template>
  <div class="dash">
    <div class="dash-head">
      <h1>Admin dashboard</h1>
      <p class="small">What producers are raising, in aggregate. Only counts are shown: no names, IDs or summaries.</p>
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
      <button v-if="!hasSample" class="btn-text" @click="loadSample">Load sample data (60 synthetic records)</button>
    </div>

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
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style>
