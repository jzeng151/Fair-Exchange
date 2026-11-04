<script setup lang="ts">
// The answer FEX gives a producer, designed to keep scrolling short and to inform, not direct:
//  - a 2–3 sentence summary comes first
//  - details come as cards the producer taps through at their own pace
//  - sources / standards / evidence strength are tucked behind "Where does this come from?"
//  - peer examples are a neutral list with trade-offs; the last card hands the decision back
import { ref, computed } from 'vue'
import DataChart from './DataChart.vue'
import PeerMap from './PeerMap.vue'
import TakeawayCard from './TakeawayCard.vue'
import FexMark from './FexMark.vue'

import type { Copy, Lang } from '../data/i18n'
import type { Scenario } from '../data/scenarios'
const props = defineProps<{
  producer: Scenario; lang: Lang; sub: boolean; en: Copy; t: Copy
  challenge: string; challengeEn: string; takeawayText: string; active: boolean
}>()
const emit = defineEmits<{ done: [] }>()

const step = ref(0)
const STEPS = 4
const open = ref<Record<string, boolean>>({}) // which "Where does this come from?" panels are open
const selectedPeer = ref<number | null>(null)
const showEn = computed(() => props.sub && props.lang !== 'en')
const titles = computed(() => [props.t.inShort, props.t.dataHeading, props.t.peersHeading, props.t.yourSummary])
const titlesEn = ['In short', 'What the data shows', 'What others have tried', 'Your summary']
const icons = ['💡', '🌧️', '🤝', '📋']
type Strength = 'exact' | 'nearest' | 'limited'
function toggle(key: string) { open.value = { ...open.value, [key]: !open.value[key] } }
function strengthIcon(s: Strength) { return s === 'exact' ? '●' : s === 'nearest' ? '◐' : '○' }
function strengthClass(s: Strength) { return ({ exact: 'ok', nearest: 'mid', limited: 'low' } as const)[s] }
function next() { if (step.value < STEPS - 1) step.value++; else emit('done') }
</script>

<template>
  <div class="answer">
    <!-- Step indicator -->
    <div class="steps" role="tablist" :aria-label="t.cardOf(step + 1, STEPS)">
      <button v-for="(s, i) in STEPS" :key="i" role="tab" :aria-selected="step === i"
              :class="['dot', { on: step === i, seen: i < step }]" @click="step = i">
        <span aria-hidden="true">{{ icons[i] }}</span> {{ i + 1 }}<span class="sr-only"> {{ titles[i] }}</span>
      </button>
    </div>
    <h3 class="card-title">{{ titles[step] }}<span v-if="showEn" class="sub-inline"> ({{ titlesEn[step] }})</span></h3>

    <!-- Card 1: in short (2–3 sentences) -->
    <section v-if="step === 0" class="card-step">
      <div class="intro-row">
        <FexMark :size="40" />
        <p class="intro">{{ t.respondIntro }}<span v-if="showEn" class="sub">{{ en.respondIntro }}</span></p>
      </div>
      <div class="summary">
        <p>{{ producer.summary[lang] }}</p>
        <p v-if="showEn" class="sub">{{ producer.summary.en }}</p>
      </div>
    </section>

    <!-- Card 2: what the data shows -->
    <section v-else-if="step === 1" class="card-step">
      <DataChart :chart="producer.chart" :lang="lang" :sub="sub" :en="en" :t="t" />
      <ul class="facts">
        <li v-for="(i, n) in producer.insights" :key="'i' + n">
          <p>{{ i.text[lang] }}<span v-if="showEn" class="sub">{{ i.text.en }}</span></p>
          <button class="where" :aria-expanded="!!open['i' + n]" @click="toggle('i' + n)">
            {{ open['i' + n] ? t.hideDetails : t.whereFrom }}<span v-if="showEn" class="sub-inline"> ({{ open['i' + n] ? en.hideDetails : en.whereFrom }})</span>
          </button>
          <div v-if="open['i' + n]" class="details">
            <span :class="['label', strengthClass(i.strength)]">{{ strengthIcon(i.strength) }} {{ t.strength[i.strength] }}<em v-if="showEn" class="sub-inline"> ({{ en.strength[i.strength] }})</em></span>
            <span>{{ t.source }}: {{ i.source }} · {{ i.period }}</span>
            <span>{{ t.clause }}: {{ i.clause }}</span>
          </div>
        </li>
      </ul>
    </section>

    <!-- Card 3: what others have tried (neutral, with trade-offs) -->
    <section v-else-if="step === 2" class="card-step">
      <p class="muted">{{ t.othersIntro }}<span v-if="showEn" class="sub">{{ en.othersIntro }}</span></p>
      <PeerMap :home="producer" :peers="producer.peers" :lang="lang" :sub="sub" :en="en" :t="t" :selected="selectedPeer" @select="(n) => (selectedPeer = n)" />
      <ul class="facts">
        <li v-for="(x, n) in producer.peers" :key="'p' + n" :class="{ active: selectedPeer === n + 1 }" @click="selectedPeer = n + 1">
          <p><span class="peer-badge">{{ n + 1 }}</span> {{ x.text[lang] }}<span v-if="showEn" class="sub">{{ x.text.en }}</span></p>
          <p v-if="x.tradeoff" class="tradeoff">
            <strong>{{ t.keepInMind }}:</strong> {{ x.tradeoff[lang] || x.tradeoff.en }}
            <span v-if="showEn && x.tradeoff.es" class="sub">{{ en.keepInMind }}: {{ x.tradeoff.en }}</span>
          </p>
          <button class="where" :aria-expanded="!!open['p' + n]" @click.stop="toggle('p' + n)">
            {{ open['p' + n] ? t.hideDetails : t.whereFrom }}<span v-if="showEn" class="sub-inline"> ({{ open['p' + n] ? en.hideDetails : en.whereFrom }})</span>
          </button>
          <div v-if="open['p' + n]" class="details">
            <span class="label neutral">{{ t.matched }}: {{ t.crop }} {{ x.match.crop ? '✓' : '✗' }}, {{ t.entityW }} {{ x.match.entity ? '✓' : '✗' }}, {{ t.country }} {{ x.match.country ? '✓' : '✗' }}</span>
            <span>{{ t.source }}: {{ x.org }} · {{ x.place }}</span>
            <span>{{ t.clause }}: {{ x.clause }}</span>
          </div>
        </li>
      </ul>
    </section>

    <!-- Card 4: summary to keep + hand the decision back -->
    <section v-else class="card-step">
      <TakeawayCard compact :producer="producer" :lang="lang" :sub="sub" :en="en" :t="t"
                    :challenge="challenge" :challenge-en="challengeEn" :text="takeawayText" />
      <p class="handback">💚 {{ t.handback }}<span v-if="showEn" class="sub">{{ en.handback }}</span></p>
    </section>

    <!-- Navigation -->
    <div class="nav">
      <button v-if="step > 0" class="btn-text" @click="step--">← {{ t.back }}<span v-if="showEn" class="sub-inline"> ({{ en.back }})</span></button>
      <span class="count">{{ t.cardOf(step + 1, STEPS) }}</span>
      <button v-if="step < STEPS - 1 || active" class="btn-primary" @click="next">
        {{ step < STEPS - 1 ? t.next : t.continueBtn }} →<span v-if="showEn"> / {{ step < STEPS - 1 ? en.next : en.continueBtn }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.intro-row { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; }
.intro { margin: 0; }
.card-title { margin: 4px 0 6px; font-size: 16px; }
.summary { background: var(--ft-ui-primary-tint); border-radius: 10px; padding: 12px 14px; }
.summary p { margin: 4px 0 0; font-size: 17px; line-height: 1.5; }
.steps { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.dot { flex: 1 1 0; min-height: 44px; padding: 6px 4px; white-space: nowrap; border: 1px solid var(--ft-ui-border); border-radius: 22px; background: var(--ft-ui-surface); cursor: pointer; font-size: 13px; color: var(--ft-ui-text-secondary); }
.dot.seen { border-color: var(--ft-ui-primary); color: var(--ft-ui-primary); }
.dot.on { background: var(--ft-ui-primary); border-color: var(--ft-ui-primary); color: #fff; font-weight: 500; }
.card-step { animation: rise .25s ease-out; }
.facts { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 10px; }
.facts li { border: 1px solid var(--ft-ui-border); border-radius: 8px; padding: 8px 10px; transition: background .2s; font-size: 15px; }
.facts li.active { background: var(--ft-ui-primary-tint); }
.facts p { margin: 0; }
.tradeoff { margin-top: 6px !important; font-size: 14px; color: var(--ft-ui-text); background: #F5F5F5; border-radius: 6px; padding: 6px 8px; }
.where { margin-top: 6px; min-height: 36px; padding: 4px 0; background: none; border: 0; color: var(--ft-ui-primary); cursor: pointer; font-size: 14px; text-decoration: underline; text-underline-offset: 3px; }
.details { display: flex; flex-direction: column; gap: 2px; margin-top: 4px; font-size: 13px; color: var(--ft-ui-text-secondary); }
.muted { margin: 0 0 6px; color: var(--ft-ui-text-secondary); font-size: 14px; }
.handback { margin: 12px 0 0; padding: 10px 12px; border-radius: 8px; background: var(--ft-ui-success-bg); font-weight: 500; }
.nav { display: flex; align-items: center; gap: 8px; margin-top: 14px; }
.nav .count { margin-left: auto; font-size: 13px; color: var(--ft-ui-text-secondary); }
.nav .btn-primary { white-space: nowrap; }
@keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .card-step { animation: none; } }
</style>
