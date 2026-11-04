<script setup lang="ts">
// "Your record" view (#32, Journey: a producer reviews what Fair Trade USA stored). Read-only: it
// lists the producer's decided, closed records and shows what was stored, with consent, in their
// language. No edit or delete controls; a fixed note points the producer to FTUSA for changes.
// Demo mode: records come from this browser (demoStore) until GET /me/records (#32) is connected.
import { computed, ref } from 'vue'
import type { ConversationRecord } from '../../../api/src/types/conversation-record'
import { t, type Lang } from '../data/i18n'
import { loadRecords } from '../lib/demoStore'
import { tagName, yourRecords, type YourRecordRow } from '../lib/yourRecord'

const props = defineProps<{
  // The signed-in producer. In demo mode the caller passes the active scenario's id; in production it
  // comes from the identity (#11), never chosen in the view.
  producerId: string
  lang?: Lang
}>()

const all = ref<ConversationRecord[]>(loadRecords())
function refresh() {
  all.value = loadRecords()
}
defineExpose({ refresh })

const lang = computed<Lang>(() => props.lang ?? 'en')
const copy = computed(() => t[lang.value].yourRecord)
const rows = computed<YourRecordRow[]>(() => yourRecords(all.value, props.producerId))
const selectedId = ref<string | null>(null)
const selected = computed<YourRecordRow | null>(
  () => rows.value.find((r) => r.recordId === selectedId.value) ?? rows.value[0] ?? null,
)

const date = (iso: string) => new Date(iso).toLocaleDateString(lang.value)
const tr = (tag: string) => tagName(tag, lang.value)
</script>

<template>
  <section class="your-record">
    <header>
      <h2>{{ copy.title }}</h2>
      <p class="intro">{{ copy.intro }}</p>
    </header>

    <p v-if="rows.length === 0" class="empty">{{ copy.empty }}</p>

    <div v-else class="layout">
      <ul class="record-list" aria-label="Your records">
        <li v-for="r in rows" :key="r.recordId">
          <button
            type="button"
            :class="{ active: selected?.recordId === r.recordId, declined: r.status === 'declined' }"
            :aria-current="selected?.recordId === r.recordId ? 'true' : undefined"
            @click="selectedId = r.recordId"
          >
            <span class="when">{{ date(r.closedAt) }}</span>
            <span v-if="r.status === 'declined'" class="declined-label">{{ copy.scope.declined }}</span>
            <span v-else class="tag-line">{{ (r.tags ?? []).map(tr).join(' · ') }}</span>
          </button>
        </li>
      </ul>

      <article v-if="selected" class="record-detail">
        <template v-if="selected.status === 'declined'">
          <p class="declined-detail">{{ copy.scope.declined }}</p>
          <p class="when">{{ date(selected.closedAt) }}</p>
        </template>

        <template v-else>
          <dl>
            <dt>{{ copy.consent }}</dt>
            <dd>
              {{ selected.consentScope === 'internal_and_outward' ? copy.scope.internal_and_outward : copy.scope.internal }}
              <span v-if="selected.consentAt" class="when"> · {{ date(selected.consentAt) }}</span>
            </dd>

            <dt>{{ copy.summary }}</dt>
            <dd>
              {{ selected.summary }}
              <em v-if="selected.changedByReviewer" class="reviewer-note">{{ copy.changedByReviewer }}</em>
            </dd>

            <dt>{{ copy.tags }}</dt>
            <dd>
              <span v-for="tag in selected.tags ?? []" :key="tag" class="tag">{{ tr(tag) }}</span>
            </dd>

            <template v-if="(selected.insights ?? []).length">
              <dt>{{ copy.insights }}</dt>
              <dd>
                <ul>
                  <li v-for="(c, i) in selected.insights" :key="'i' + i">
                    {{ c.text }} <span class="cite">({{ c.source }} · {{ c.clause }})</span>
                  </li>
                </ul>
              </dd>
            </template>

            <template v-if="(selected.peerExamples ?? []).length">
              <dt>{{ copy.peers }}</dt>
              <dd>
                <ul>
                  <li v-for="(c, i) in selected.peerExamples" :key="'p' + i">
                    {{ c.text }} <span class="cite">({{ c.source }} · {{ c.clause }})</span>
                  </li>
                </ul>
              </dd>
            </template>

            <template v-if="selected.feedback">
              <dt>{{ copy.feedback }}</dt>
              <dd>{{ copy.feedbackValue[selected.feedback] }}</dd>
            </template>

            <dt>{{ copy.reviewStatus }}</dt>
            <dd>{{ selected.reviewStatus === 'reviewed' ? copy.reviewed : copy.pending }}</dd>
          </dl>
        </template>
      </article>
    </div>

    <p class="contact" role="note">{{ copy.contact }}</p>
  </section>
</template>

<style scoped>
.your-record { max-width: 60rem; margin: 0 auto; }
.intro { color: var(--muted, #555); }
.layout { display: grid; grid-template-columns: 16rem 1fr; gap: 1rem; }
.record-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.25rem; }
.record-list button { width: 100%; text-align: left; display: flex; flex-direction: column; gap: 0.15rem; padding: 0.5rem 0.75rem; border: 1px solid #ddd; border-radius: 0.5rem; background: #fff; cursor: pointer; }
.record-list button.active { border-color: #2b7; background: #f3fbf6; }
.record-list button.declined { color: #777; }
.when { font-size: 0.85rem; color: #777; }
.tag { display: inline-block; margin: 0 0.3rem 0.3rem 0; padding: 0.1rem 0.5rem; background: #eef; border-radius: 1rem; font-size: 0.85rem; }
.cite { color: #777; font-size: 0.85rem; }
.reviewer-note { display: block; color: #a60; font-style: italic; font-size: 0.85rem; }
.contact { margin-top: 1.5rem; padding: 0.75rem 1rem; background: #f7f7f7; border-left: 3px solid #2b7; border-radius: 0.25rem; }
dt { font-weight: 600; margin-top: 0.75rem; }
dd { margin: 0.15rem 0 0; }
</style>
