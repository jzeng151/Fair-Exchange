<script setup lang="ts">
import { ref } from 'vue'
import FexMark from './FexMark.vue'

import type { Copy, Lang } from '../data/i18n'
import type { Scenario } from '../data/scenarios'
const props = withDefaults(defineProps<{
  producer: Scenario; lang: Lang; sub: boolean; en: Copy; t: Copy
  challenge: string; challengeEn: string; text: string
  compact?: boolean // on screen: just the essentials; print shows everything
}>(), { compact: false })
const copied = ref(false)
const today = new Date().toLocaleDateString(props.lang === 'es' ? 'es-CO' : 'en-US', { year: 'numeric', month: 'long', day: 'numeric' })

async function copy() {
  try { await navigator.clipboard.writeText(props.text); copied.value = true; setTimeout(() => (copied.value = false), 1500) } catch { /* ignore */ }
}
function print() { window.print() }
const showEn = () => props.sub && props.lang !== 'en'
</script>

<template>
  <article class="takeaway-card">
    <header class="tc-head">
      <FexMark :size="44" />
      <div>
        <div class="tc-title">{{ t.cardTitle }}</div>
        <div class="tc-meta">{{ producer.name }} · {{ producer.region }} · {{ today }}</div>
      </div>
    </header>

    <section>
      <h4>💬 {{ t.takeaway.challenge }}<span v-if="showEn()" class="sub-inline"> ({{ en.takeaway.challenge }})</span></h4>
      <p class="quote">“{{ challenge }}”</p>
      <p v-if="showEn()" class="sub">“{{ challengeEn }}”</p>
    </section>

    <section v-if="compact" class="screen-only">
      <h4>💡 {{ t.inShort }}<span v-if="showEn()" class="sub-inline"> ({{ en.inShort }})</span></h4>
      <p class="short">{{ producer.summary[lang] }}</p>
      <p v-if="showEn()" class="sub">{{ producer.summary.en }}</p>
    </section>

    <section :class="{ 'print-only': compact }">
      <h4>📊 {{ t.takeaway.data }}<span v-if="showEn()" class="sub-inline"> ({{ en.takeaway.data }})</span></h4>
      <ul>
        <li v-for="(i, n) in producer.insights" :key="n">
          {{ i.text[lang] }}<span v-if="showEn()" class="sub">{{ i.text.en }}</span>
          <span class="src">{{ i.source }}</span>
        </li>
      </ul>
    </section>

    <section :class="{ 'print-only': compact }">
      <h4>🤝 {{ t.takeaway.others }}<span v-if="showEn()" class="sub-inline"> ({{ en.takeaway.others }})</span></h4>
      <ul>
        <li v-for="(x, n) in producer.peers" :key="n">
          {{ x.text[lang] }}<span v-if="showEn()" class="sub">{{ x.text.en }}</span>
          <span class="src">{{ x.org }} · {{ x.place }}</span>
        </li>
      </ul>
    </section>

    <footer class="tc-foot">{{ t.cardFooter }}</footer>

    <div class="tc-actions no-print">
      <button class="btn-default" @click="print">🖨 {{ t.printCard }}<span v-if="showEn()" class="sub-inline"> ({{ en.printCard }})</span></button>
      <button class="btn-text" @click="copy">{{ copied ? '✓ ' + t.copied : t.copy }}</button>
    </div>
  </article>
</template>

<style scoped>
.takeaway-card { border: 1px solid var(--ft-ui-border); border-radius: 12px; overflow: hidden; background: var(--ft-ui-surface); margin-top: 8px; }
.tc-head { display: flex; gap: 12px; align-items: center; padding: 14px 16px; background: var(--ft-brand-indigo); color: #fff; }
.tc-avatar { width: 44px; height: 44px; border-radius: 50%; border: 2px solid var(--ft-brand-green); flex: none; background: #fff; }
.tc-title { font-family: var(--ft-font-brand-heading); font-weight: 600; font-size: 18px; }
.tc-meta { font-size: 13px; opacity: .85; }
section { padding: 10px 16px 0; }
h4 { margin: 4px 0 6px; font-size: 15px; font-weight: 500; }
.quote { margin: 0 0 4px; font-style: italic; }
.short { margin: 0 0 4px; }
.print-only { display: none; }
@media print { .print-only { display: block; } .screen-only { display: none; } }
ul { margin: 0; padding-left: 18px; }
li { margin-bottom: 8px; }
.src { display: block; font-size: 12px; color: var(--ft-ui-text-secondary); }
.tc-foot { margin-top: 10px; padding: 10px 16px; font-size: 12px; color: var(--ft-ui-text-secondary); border-top: 1px solid var(--ft-ui-border); }
.tc-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 0 16px 14px; }
</style>
