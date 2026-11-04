<script setup lang="ts">
import type { Copy, Lang } from '../data/i18n'
defineProps<{ steps: { active: boolean; done: boolean }[]; lang: Lang; sub: boolean; en: Copy; t: Copy }>()
const ICONS = ['📋', '🌦️', '🤝', '📖']
</script>

<template>
  <div class="checklist" role="status" aria-live="polite">
    <p class="cl-title">
      {{ steps.every(s => s.done) ? '✅ ' + t.done : t.checking + '…' }}
      <span v-if="sub && lang !== 'en'" class="sub-inline">({{ steps.every(s => s.done) ? en.done : en.checking }})</span>
    </p>
    <ol>
      <li v-for="(s, i) in steps" :key="i" :class="{ done: s.done, active: s.active }">
        <span class="icon" aria-hidden="true">{{ ICONS[i] }}</span>
        <span class="label-text">{{ t.steps[i] }}<span v-if="sub && lang !== 'en'" class="sub">{{ en.steps[i] }}</span></span>
        <span class="state" aria-hidden="true">
          <span v-if="s.done" class="tick">✓</span>
          <span v-else-if="s.active" class="spinner"></span>
        </span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.checklist { align-self: flex-start; width: min(100%, 360px); border: 1px solid var(--ft-ui-border); border-radius: 10px; background: var(--ft-ui-surface); padding: 12px 14px; }
.cl-title { margin: 0 0 8px; font-weight: 500; }
ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
li { display: grid; grid-template-columns: 28px 1fr 22px; align-items: center; gap: 8px; opacity: .45; transition: opacity .25s; }
li.active, li.done { opacity: 1; }
.icon { font-size: 20px; text-align: center; }
li.active .icon { animation: bob .8s ease-in-out infinite; }
.tick { display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; background: var(--ft-ui-success); color: #fff; font-size: 12px; animation: pop .25s ease-out; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--ft-ui-border); border-top-color: var(--ft-ui-primary); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes bob { 50% { transform: translateY(-3px); } }
@keyframes pop { from { transform: scale(.4); } to { transform: scale(1); } }
@media (prefers-reduced-motion: reduce) { li.active .icon, .spinner, .tick { animation: none; } }
</style>
