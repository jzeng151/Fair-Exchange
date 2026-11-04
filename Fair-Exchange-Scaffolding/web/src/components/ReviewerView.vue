<script setup lang="ts">
// Reviewer view (issue #31, Journey 3): an Impact, Research & Learning reviewer checks a record,
// approves or corrects its tags and summary, and the record is marked reviewed.
// Demo mode: records come from this browser (chat + "Load demo records") until the review API (#27).
import { computed, reactive, ref, watch } from 'vue'
import type { CompletedRecord, ConversationRecord } from '../../../../api/src/types/conversation-record'
import { CHALLENGE_TAGS } from '../data/scenarios'
import { demoRecords } from '../lib/demoSeed'
import { clearDemoData, loadRecords, loadTrace, saveRecord, saveTrace, updateRecord } from '../lib/demoStore'
import { ReviewError, reviewRecord } from '../lib/review'

const records = ref<ConversationRecord[]>(loadRecords())
const selectedId = ref<string | null>(records.value[0]?.record_id ?? null)
const filter = ref<'all' | 'pending' | 'reviewed' | 'flagged' | 'declined'>('all')
const reviewer = ref('IRL reviewer (demo)')
const error = ref('')
const saved = ref('')
const draft = reactive<{ tags: string[]; summaryOriginal: string; summaryEnglish: string }>({ tags: [], summaryOriginal: '', summaryEnglish: '' })

function refresh() { records.value = loadRecords() }
defineExpose({ refresh })

const visible = computed(() => records.value.filter((r) => {
  if (filter.value === 'all') return true
  if (filter.value === 'declined') return r.status === 'declined'
  if (r.status !== 'completed') return false
  if (filter.value === 'flagged') return r.pii_flag === true
  return r.review_status === filter.value
}))
const selected = computed(() => records.value.find((r) => r.record_id === selectedId.value) ?? visible.value[0] ?? null)
const completed = computed<CompletedRecord | null>(() => (selected.value?.status === 'completed' ? selected.value : null))
const trace = computed(() => (selected.value ? loadTrace(selected.value.record_id) : []))

// Reset the form only when a DIFFERENT record is selected. Reloading the list after a save
// produces a new object for the same record; that must not wipe the confirmation message.
watch(() => completed.value?.record_id, () => {
  const r = completed.value
  error.value = ''; saved.value = ''
  draft.tags = r ? [...r.tags] : []
  draft.summaryOriginal = r?.summary_original ?? ''
  draft.summaryEnglish = r?.summary_english ?? ''
}, { immediate: true })

const changed = computed(() => {
  const r = completed.value
  if (!r) return false
  return draft.tags.join('|') !== r.tags.join('|') || draft.summaryOriginal !== r.summary_original
    || (r.language !== 'en' && draft.summaryEnglish !== (r.summary_english ?? ''))
})

function toggleTag(tag: string) {
  draft.tags = draft.tags.includes(tag) ? draft.tags.filter((t) => t !== tag) : [...draft.tags, tag]
}

function approve() {
  const r = completed.value
  if (!r) return
  const corrected = changed.value // read before the reload resets the comparison
  try {
    const updated = reviewRecord(r, {
      tags: draft.tags,
      summaryOriginal: draft.summaryOriginal,
      ...(r.language !== 'en' ? { summaryEnglish: draft.summaryEnglish } : {}),
    }, reviewer.value, new Date())
    updateRecord(updated)
    refresh()
    error.value = ''
    saved.value = corrected ?'Corrections saved and record marked reviewed.' : 'Record approved and marked reviewed.'
  } catch (e) {
    saved.value = ''
    error.value = e instanceof ReviewError ? e.message : 'Could not save the review.'
  }
}

function loadDemo() {
  const { records: demo, traces } = demoRecords(new Date())
  for (const r of [...demo].reverse()) saveRecord(r)
  for (const [id, steps] of Object.entries(traces)) saveTrace(id, steps)
  refresh()
  selectedId.value = demo[0]?.record_id ?? null
}

function clearAll() {
  clearDemoData(); refresh(); selectedId.value = null
}

const fmt = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : '—')
const LANGS: Record<string, string> = { es: 'Spanish', en: 'English' }
const FILTERS = ['all', 'pending', 'reviewed', 'flagged', 'declined'] as const
</script>

<template>
  <div class="review">
    <div class="review-head">
      <h1>Records to review</h1>
      <p class="small">Demo mode: records saved in this browser by the producer chat, until the review API (#27) is connected.</p>
    </div>

    <div v-if="!records.length" class="panel empty">
      <p><strong>No records yet.</strong> Complete a conversation on the Producer side and save it, or load a few demo records.</p>
      <button class="btn-primary" @click="loadDemo">Load demo records</button>
    </div>

    <div v-else class="layout review-layout">
      <section class="panel detail" aria-label="Record detail">
        <template v-if="selected">
          <div class="detail-head">
            <h2>{{ selected.record_id }}</h2>
            <span v-if="selected.status === 'declined'" class="label neutral">Declined</span>
            <span v-else :class="['label', selected.review_status === 'reviewed' ? 'ok' : 'mid']">
              {{ selected.review_status === 'reviewed' ? '✓ Reviewed' : 'Pending review' }}
            </span>
          </div>

          <dl class="kv">
            <dt>Producer ID</dt><dd>{{ selected.producer_id }}</dd>
            <dt>Saved</dt><dd>{{ fmt(selected.created_at) }}</dd>
            <dt>Source</dt><dd>{{ selected.source }}</dd>
            <dt>Consent</dt><dd>{{ selected.consent.scope }}</dd>
            <template v-if="completed">
              <dt>Entity type</dt><dd>{{ completed.entity_type }}</dd>
              <dt>Language</dt><dd>{{ LANGS[completed.language] ?? completed.language }}</dd>
              <dt>Helpful?</dt><dd>{{ completed.feedback ?? '—' }}</dd>
              <dt v-if="completed.reviewed_by">Reviewed by</dt><dd v-if="completed.reviewed_by">{{ completed.reviewed_by }} · {{ fmt(completed.reviewed_at) }}</dd>
            </template>
          </dl>

          <div v-if="selected.status === 'declined'" class="alert info">
            The producer declined. By design this record holds only identifiers, status and time: no summary, tags or feedback. There is nothing to review.
          </div>

          <template v-if="completed">
            <div v-if="completed.pii_flag" class="alert warning" role="status">
              ⚑ <strong>Personal information flagged for review.</strong> A name or contact detail was mentioned. Nothing has been removed.
            </div>

            <h3>Summary in the producer’s words</h3>
            <div :class="['summary-grid', { two: completed.language !== 'en' }]">
              <label><span>{{ LANGS[completed.language] ?? completed.language }} (original)</span>
                <textarea v-model="draft.summaryOriginal" rows="3"></textarea></label>
              <label v-if="completed.language !== 'en'"><span>English</span>
                <textarea v-model="draft.summaryEnglish" rows="3"></textarea></label>
            </div>

            <h3>Challenge tags</h3>
            <div class="tag-set" role="group" aria-label="Challenge tags">
              <button v-for="tag in CHALLENGE_TAGS" :key="tag" :class="['chip', { on: draft.tags.includes(tag) }]"
                      :aria-pressed="draft.tags.includes(tag)" @click="toggleTag(tag)">
                {{ draft.tags.includes(tag) ? '✓ ' : '' }}{{ tag }}
              </button>
            </div>

            <h3>What FEX told the producer</h3>
            <ul class="guidance">
              <li v-for="(c, n) in [...(completed.insights ?? []), ...(completed.peer_examples ?? [])]" :key="n">
                {{ c.text }}
                <span class="small"> · {{ c.citation.source }} · {{ c.citation.standard_clause }} · {{ c.citation.strength }}</span>
              </li>
            </ul>

            <h3>Agent reasoning</h3>
            <ol v-if="trace.length" class="log">
              <li v-for="(s, n) in trace" :key="n"><span class="time">{{ s.time }}</span> <code>{{ s.tool }}</code> {{ s.detail }}</li>
            </ol>
            <p v-else class="small">No trace stored. In production this comes from AgentCore Observability.</p>

            <div class="approve-row">
              <label class="reviewer"><span>Reviewer</span><input v-model="reviewer" /></label>
              <button class="btn-primary" @click="approve">{{ changed ? 'Save corrections and mark reviewed' : 'Approve and mark reviewed' }}</button>
            </div>
            <p v-if="error" class="alert danger" role="alert">{{ error }}</p>
            <p v-if="saved" class="alert success" role="status">✓ {{ saved }}</p>
            <p class="small">Approval means a person checked this record. It is not verified fact or certification evidence.</p>
          </template>
        </template>
      </section>

      <section class="panel list-panel" aria-label="Records">
        <div class="btn-group" role="group" aria-label="Filter records">
          <button v-for="f in FILTERS" :key="f" :class="{ active: filter === f }" @click="filter = f">{{ f }}</button>
        </div>
        <p v-if="!visible.length" class="small">No records match this filter.</p>
        <ul class="record-list">
          <li v-for="r in visible" :key="r.record_id">
            <button :class="{ active: selected?.record_id === r.record_id }" @click="selectedId = r.record_id">
              <strong>{{ r.record_id }}</strong> · {{ r.producer_id }}
              <span v-if="r.status === 'declined'" class="label neutral">Declined</span>
              <span v-else :class="['label', r.review_status === 'reviewed' ? 'ok' : 'mid']">{{ r.review_status === 'reviewed' ? 'Reviewed' : 'Pending' }}</span>
              <span v-if="r.status === 'completed' && r.pii_flag" class="label low">⚑ PII</span>
              <br /><span class="small">{{ fmt(r.created_at) }}</span>
            </button>
          </li>
        </ul>
        <div class="list-actions">
          <button class="btn-text" @click="loadDemo">Load demo records</button>
          <button class="btn-text" @click="clearAll">Clear demo data</button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.review-head h1 { font-family: var(--ft-font-brand-heading); color: var(--ft-brand-indigo); font-size: 26px; margin: 0 0 2px; }
.review-head { margin-bottom: 12px; }
.empty { text-align: center; padding: 28px; }
.review-layout { grid-template-columns: 8fr 4fr; }
.review-layout > .panel { min-width: 0; } /* let grid cells shrink on phones */
.list-panel .btn-group { flex-wrap: wrap; }
.detail-head { display: flex; align-items: center; gap: 10px; }
.detail-head h2 { margin: 0; }
.alert.danger { background: var(--ft-ui-error-bg); border-color: var(--ft-ui-error); }
.alert.success { background: var(--ft-ui-success-bg); border-color: var(--ft-ui-success); }
.approve-row { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; margin-top: 16px; }
.reviewer { display: grid; gap: 2px; font-size: 14px; }
.reviewer span { color: var(--ft-ui-text-secondary); }
.list-actions { display: flex; justify-content: space-between; margin-top: 10px; }
@media (max-width: 900px) { .review-layout { grid-template-columns: 1fr; } }
</style>
