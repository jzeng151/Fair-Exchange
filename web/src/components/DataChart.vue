<script setup lang="ts">
// Single-series bar chart: one blue hue for the data, a neutral gray reference bar.
// Values are labeled on the reference and the latest bar only; every bar has a hover tooltip.
import { computed, ref } from 'vue'

import type { Copy, Lang } from '../data/i18n'
import type { Peer, Scenario } from '../data/scenarios'
const props = defineProps<{ chart: Scenario['chart']; lang: Lang; sub: boolean; en: Copy; t: Copy }>()

const W = 320, H = 140, PAD_L = 8, PAD_R = 8, TOP = 20, BOTTOM = 24
const hover = ref<number | null>(null)

const bars = computed(() => {
  const list = props.chart.bars
  const max = Math.max(...list.map((b) => b.value)) * 1.12
  const plotH = H - TOP - BOTTOM
  const slot = (W - PAD_L - PAD_R) / list.length
  const bw = Math.min(44, slot - 2 - 12)
  return list.map((b, i) => {
    const h = (b.value / max) * plotH
    const x = PAD_L + i * slot + (slot - bw) / 2
    return { ...b, x, w: bw, y: TOP + plotH - h, h, cx: x + bw / 2, showValue: b.ref || i === list.length - 1 }
  })
})
const baseY = H - BOTTOM
function fmt(v: number) { return props.chart.unit.startsWith('US$') ? v.toFixed(2) : String(v) }
// rounded top corners (4px), square at the baseline
function barPath(b: { x: number; y: number; w: number; h: number }) {
  const r = Math.min(4, b.w / 2, b.h)
  return `M${b.x},${b.y + b.h} V${b.y + r} Q${b.x},${b.y} ${b.x + r},${b.y} H${b.x + b.w - r} Q${b.x + b.w},${b.y} ${b.x + b.w},${b.y + r} V${b.y + b.h} Z`
}
const summary = computed(() => props.chart.bars.map((b) => `${b.label.en}: ${fmt(b.value)} ${props.chart.unit}`).join('; '))
</script>

<template>
  <figure class="chart">
    <figcaption class="chart-title">
      {{ chart.title[lang] }} <span class="chart-unit">({{ chart.unit }})</span>
      <span v-if="sub && lang !== 'en'" class="sub">{{ chart.title.en }}</span>
    </figcaption>
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="`${chart.title.en}. ${summary}`">
      <line :x1="PAD_L" :x2="W - PAD_R" :y1="baseY" :y2="baseY" class="axis" />
      <g v-for="(b, i) in bars" :key="i" @mouseenter="hover = i" @mouseleave="hover = null" @focus="hover = i" @blur="hover = null" tabindex="0">
        <rect :x="b.x - 6" :y="TOP - 4" :width="b.w + 12" :height="baseY - TOP + 4" fill="transparent" />
        <path :d="barPath(b)" :class="['bar', { ref: b.ref, dim: hover !== null && hover !== i }]" />
        <text v-if="b.showValue || hover === i" :x="b.cx" :y="b.y - 6" text-anchor="middle" class="val">{{ fmt(b.value) }}</text>
        <text :x="b.cx" :y="baseY + 16" text-anchor="middle" class="lbl">{{ b.label[lang] }}</text>
        <title>{{ b.label[lang] }}: {{ fmt(b.value) }} {{ chart.unit }}</title>
      </g>
    </svg>
    <p class="chart-note">
      {{ t.chartNote }}<span v-if="sub && lang !== 'en'" class="sub-inline"> ({{ en.chartNote }})</span>
      · {{ t.source }}: {{ chart.source }}
    </p>
  </figure>
</template>

<style scoped>
.chart { margin: 8px 0 16px; padding: 12px; border: 1px solid var(--ft-ui-border); border-radius: 8px; background: var(--ft-ui-surface); }
.chart-title { font-weight: 500; font-size: 15px; margin-bottom: 6px; }
.chart-unit { color: var(--ft-ui-text-secondary); font-weight: 400; }
svg { width: 100%; height: auto; display: block; overflow: visible; }
.axis { stroke: #D6D6D6; stroke-width: 1; }
.bar { fill: var(--ft-ui-primary); transition: opacity .15s; }
.bar.ref { fill: #7C7E7F; }
.bar.dim { opacity: .45; }
.val { font-size: 12px; font-weight: 500; fill: var(--ft-ui-text); }
.lbl { font-size: 11px; fill: rgba(0, 0, 0, .6); }
g:focus { outline: none; }
g:focus-visible .bar { stroke: var(--ft-ui-text); stroke-width: 2; }
.chart-note { margin: 6px 0 0; font-size: 13px; color: var(--ft-ui-text-secondary); }
</style>
