<script setup lang="ts">
// One breakdown as horizontal bars (single series: one hue, no legend, value at the bar tip).
// Hidden groups (under 5, or hidden to protect one that is) show as text with no bar, so their size isn't drawn either.
import { computed, ref } from 'vue'
import type { Breakdown } from '../lib/analytics'

const props = defineProps<{ title: string; note?: string; breakdown: Breakdown; total: number | null; asTable: boolean; labels?: Record<string, string> }>()
const hover = ref<string | null>(null)
const visible = computed(() => props.breakdown.buckets.filter((b) => b.count !== null) as { key: string; count: number }[])
const hidden = computed(() => props.breakdown.buckets.filter((b) => b.count === null))
const max = computed(() => Math.max(1, ...visible.value.map((b) => b.count)))
const name = (key: string) => props.labels?.[key] ?? key
const pct = (k: number) => (props.total ? `${Math.round((k / props.total) * 100)}%` : '')
</script>

<template>
  <section class="panel breakdown" :aria-label="title">
    <h3>{{ title }}</h3>
    <p v-if="note" class="small">{{ note }}</p>

    <table v-if="asTable" class="bd-table">
      <thead><tr><th scope="col">Group</th><th scope="col">Records</th><th scope="col">Share</th></tr></thead>
      <tbody>
        <tr v-for="b in visible" :key="b.key"><td>{{ name(b.key) }}</td><td>{{ b.count }}</td><td>{{ pct(b.count) }}</td></tr>
        <tr v-for="b in hidden" :key="b.key" class="muted"><td>{{ name(b.key) }}</td><td colspan="2">hidden for privacy</td></tr>
      </tbody>
    </table>

    <ul v-else class="bars">
      <li v-for="b in visible" :key="b.key" class="bar-row" tabindex="0"
          @mouseenter="hover = b.key" @mouseleave="hover = null" @focus="hover = b.key" @blur="hover = null">
        <span class="bar-label">{{ name(b.key) }}</span>
        <span class="bar-track">
          <span class="bar" :style="{ width: `${(b.count / max) * 100}%` }"></span>
          <span class="bar-value">{{ b.count }}</span>
        </span>
        <span v-if="hover === b.key" class="tip" role="tooltip">{{ b.count }} records · {{ pct(b.count) }} of records in view</span>
      </li>
      <li v-for="b in hidden" :key="b.key" class="bar-row hidden-row">
        <span class="bar-label">{{ name(b.key) }}</span>
        <span class="hidden-note">hidden for privacy</span>
      </li>
      <li v-if="!breakdown.buckets.length" class="small">No records in view.</li>
    </ul>
  </section>
</template>

<style scoped>
.breakdown h3 { margin: 0 0 2px; font-size: 17px; }
.bars { list-style: none; padding: 0; margin: 10px 0 0; display: grid; gap: 2px; }
.bar-row { position: relative; display: grid; grid-template-columns: minmax(110px, 38%) 1fr; align-items: center; gap: 10px; min-height: 30px; border-radius: 4px; padding: 0 4px; }
.bar-row:hover, .bar-row:focus-visible { background: var(--ft-ui-surface-subtle, #f4f6f8); outline: none; }
.bar-label { font-size: 14px; color: var(--ft-ui-text, #343637); overflow-wrap: anywhere; }
.bar-track { display: flex; align-items: center; gap: 6px; min-width: 0; }
.bar { display: block; height: 14px; min-width: 2px; background: #2C6EA1; border-radius: 0 4px 4px 0; }
.bar-value { font-size: 13px; font-variant-numeric: tabular-nums; color: var(--ft-ui-text, #343637); }
.hidden-row .bar-label, .hidden-note { color: var(--ft-ui-text-secondary, #5f6368); font-size: 13px; }
.hidden-note { font-style: italic; }
.tip { position: absolute; right: 4px; top: -26px; z-index: 2; background: #343637; color: #fff; font-size: 12px; padding: 3px 8px; border-radius: 4px; white-space: nowrap; pointer-events: none; }
.bd-table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px; }
.bd-table th, .bd-table td { text-align: left; padding: 6px 4px; border-bottom: 1px solid var(--ft-ui-border, #e2e5e8); }
.bd-table td:nth-child(2), .bd-table td:nth-child(3) { font-variant-numeric: tabular-nums; }
.bd-table .muted td { color: var(--ft-ui-text-secondary, #5f6368); font-style: italic; }
</style>
