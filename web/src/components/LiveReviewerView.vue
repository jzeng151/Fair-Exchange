<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { CompletedRecord } from '../../../api/src/types/conversation-record'
import { CHALLENGE_TAGS } from '../data/scenarios'
import { recordApi, type ReviewSummary } from '../lib/recordApi'
const props = defineProps<{ apiUrl: string }>()
const passcode = ref('')
const signedIn = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const records = ref<ReviewSummary[]>([])
const selected = ref<CompletedRecord | null>(null)
const status = ref('pending')
const pii = ref('')
const evidence = ref('')
const draft = reactive({ tags: [] as string[], original: '', english: '' })
const api = () => recordApi(props.apiUrl, { 'x-demo-reviewer-passcode': passcode.value })
const readonly = computed(() => selected.value?.review_status === 'reviewed')
const unresolved = computed(() => selected.value?.pii_flag && !selected.value.pii_review)
watch(passcode, () => { signedIn.value = false; selected.value = null; records.value = []; error.value = '' })
function setRecord(record: CompletedRecord) {
  selected.value = record
  draft.tags = [...(record.reviewer_tags ?? record.tags)]
  draft.original = record.reviewer_summary_original ?? record.summary_original
  draft.english = record.reviewer_summary_english ?? record.summary_english ?? ''
}
async function run(action: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (e) { error.value = e instanceof Error ? e.message : 'Unable to complete the request.' }
  finally { busy.value = false }
}
async function refresh() {
  await run(async () => {
    const identity = await api().identity()
    if (!identity.roles.includes('reviewer')) throw new Error('A reviewer sign-in is required.')
    signedIn.value = true
    const query = new URLSearchParams()
    if (status.value) query.set('review_status', status.value)
    if (pii.value) query.set('pii', pii.value)
    if (evidence.value) query.set('evidence', evidence.value)
    records.value = (await api().list(`?${query}`)).records
  })
}
async function open(id: string) { await run(async () => { setRecord(await api().get(id)) }) }
async function save(piiReview?: 'confirmed' | 'cleared') {
  const r = selected.value
  if (!r) return
  await run(async () => {
    setRecord(await api().patch(r.record_id, { version: r.version, reviewer_tags: draft.tags,
      reviewer_summary_original: draft.original,
      ...(r.language !== 'en' ? { reviewer_summary_english: draft.english } : {}),
      ...(piiReview ? { pii_review: piiReview } : {}),
    }))
    notice.value = 'Corrections saved. The agent’s original values are preserved.'
  })
}
async function approve() {
  const r = selected.value
  if (!r) return
  await run(async () => { setRecord(await api().approve(r.record_id, r.version)); notice.value = 'Record approved.' })
}
const dirty = computed(() => !!selected.value && (draft.original !== (selected.value.reviewer_summary_original ?? selected.value.summary_original)
  || draft.english !== (selected.value.reviewer_summary_english ?? selected.value.summary_english ?? '')
  || draft.tags.join('|') !== (selected.value.reviewer_tags ?? selected.value.tags).join('|')))
defineExpose({ refresh: () => { if (signedIn.value) void refresh() } })
</script>
<template>
  <div class="review">
    <h1>Records to review</h1>
    <form class="panel signin" @submit.prevent="refresh">
      <label>Reviewer passcode<input v-model="passcode" type="password" autocomplete="off" required :disabled="busy" /></label>
      <button class="btn-primary" :disabled="busy">{{ busy ? 'Loading…' : signedIn ? 'Refresh records' : 'Sign in' }}</button>
    </form>
    <p v-if="error" class="panel" role="alert">{{ error }} <button v-if="selected" :disabled="busy" @click="open(selected.record_id)">Reload record</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <div v-if="signedIn" class="review-live-layout">
      <section class="panel" aria-label="Records">
        <form class="filters" @submit.prevent="refresh">
          <label>Status<select v-model="status"><option value="">All</option><option value="pending">Pending</option><option value="reviewed">Reviewed</option></select></label>
          <label>Personal information<select v-model="pii"><option value="">All</option><option value="unresolved">Unresolved</option><option value="any">Flagged</option></select></label>
          <label>Evidence<select v-model="evidence"><option value="">All</option><option value="limited">Limited</option><option value="full">Full</option></select></label>
          <button :disabled="busy">Apply filters</button>
        </form>
        <p v-if="!records.length">No closed records match these filters.</p>
        <ul class="record-list"><li v-for="r in records" :key="r.record_id">
          <button :disabled="busy" :aria-current="selected?.record_id === r.record_id ? 'true' : undefined" @click="open(r.record_id)">
            {{ r.language }} · {{ r.entity_type }} · {{ r.review_status }}<br />{{ r.tags.join(', ') }}<br />{{ r.closed_at }}
          </button>
        </li></ul>
      </section>
      <article v-if="selected" class="panel detail" aria-label="Record detail">
        <h2>{{ selected.review_status === 'reviewed' ? 'Reviewed record' : 'Pending review' }}</h2>
        <p>{{ selected.language }} · {{ selected.entity_type }} · {{ selected.evidence }} evidence · {{ selected.closed_at }}</p>
        <p v-if="readonly">Approved records are read-only.</p>
        <h3>Summary in the producer’s language</h3>
        <p><strong>Agent original</strong><br />{{ selected.summary_original }}</p>
        <label>Reviewer version<textarea v-model="draft.original" rows="4" :readonly="readonly || busy" /></label>
        <template v-if="selected.language !== 'en'">
          <p><strong>Agent English summary</strong><br />{{ selected.summary_english }}</p>
          <label>Reviewer English version<textarea v-model="draft.english" rows="4" :readonly="readonly || busy" /></label>
        </template>
        <h3>Challenge tags</h3><p>Agent original: {{ selected.tags.join(', ') }}</p>
        <fieldset :disabled="readonly || busy"><legend>Reviewer tags</legend>
          <label v-for="tag in CHALLENGE_TAGS" :key="tag" class="tag-choice"><input v-model="draft.tags" type="checkbox" :value="tag" /> {{ tag }}</label>
        </fieldset>
        <h3>Guidance and sources</h3>
        <ul><li v-for="(c, i) in [...(selected.insights ?? []), ...(selected.peer_examples ?? [])]" :key="i">{{ c.text }}<p class="small">{{ c.citation.source }} · {{ c.citation.standard_clause }} · {{ c.citation.strength }}</p></li></ul>
        <h3>Earlier answers</h3>
        <section v-for="(answer, i) in selected.earlier_answers ?? []" :key="i"><p>{{ answer.given_at }} · {{ answer.reason }}</p><ul><li v-for="(claim, j) in [...(answer.insights ?? []), ...(answer.peer_examples ?? [])]" :key="j">{{ claim.text }} · {{ claim.citation.source }} · {{ claim.citation.standard_clause }}</li></ul></section>
        <h3>Consent</h3><p>{{ selected.consent.scope }} · {{ selected.consent.recorded_at }}</p>
        <ul><li v-for="(choice, i) in selected.consent_history ?? []" :key="i">{{ choice.scope }} · {{ choice.recorded_at }}</li></ul>
        <h3>Personal information</h3>
        <p>{{ selected.pii_flag ? 'Flagged for human review' : 'No personal information flagged' }} · {{ selected.pii_review ?? 'No review decision' }}</p>
        <ul><li v-for="(match, i) in selected.pii_matches ?? []" :key="i">{{ match.entity_type }}: {{ match.context }}</li></ul>
        <div v-if="!readonly && selected.pii_flag" class="actions"><button :disabled="busy" @click="save('confirmed')">Confirm flag and save</button><button :disabled="busy" @click="save('cleared')">Clear flag and save</button></div>
        <h3>Decision log</h3>
        <ul v-if="selected.decision_log?.length"><li v-for="(entry, i) in selected.decision_log" :key="i">{{ entry.at }} · {{ entry.kind }} · {{ entry.code }}<template v-if="entry.refs?.length"> · {{ entry.refs.join(', ') }}</template></li></ul>
        <p v-else>No decisions logged</p>
        <p>Producer feedback: {{ selected.feedback ?? 'Not provided' }}</p>
        <p v-if="selected.reviewed_by">Reviewed by {{ selected.reviewed_by }} · {{ selected.reviewed_at }}</p>
        <div v-if="!readonly" class="actions"><button :disabled="busy || !dirty" @click="save()">Save corrections</button><button class="btn-primary" :disabled="busy || dirty || !!unresolved" @click="approve">Approve record</button></div>
        <p v-if="unresolved">Resolve the PII flag first.</p><p v-if="dirty">Save your corrections before approving.</p>
      </article>
      <p v-else class="panel">Select a record to review.</p>
    </div>
  </div>
</template>
<style scoped>
.signin,.actions { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; margin-bottom: 16px; }
.review-live-layout { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(0, 2fr); gap: 16px; }
label,.filters { display: grid; gap: 6px; } .filters { gap: 12px; margin-bottom: 16px; }
input,select,textarea { padding: 8px; max-width: 100%; } textarea { width: 100%; box-sizing: border-box; }
.tag-choice { display: flex; gap: 6px; align-items: center; } .detail { overflow-wrap: anywhere; }
@media(max-width: 800px) { .review-live-layout { grid-template-columns: 1fr; } }
</style>
