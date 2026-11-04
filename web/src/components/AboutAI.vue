<script setup lang="ts">
// "How FEX uses AI": plain-language explainer for producers (and judges).
import { onMounted, onBeforeUnmount, ref } from 'vue'
import FexMark from './FexMark.vue'

import type { Copy, Lang } from '../data/i18n'
const props = defineProps<{ t: Copy; en: Copy; sub: boolean; lang: Lang }>()
const emit = defineEmits<{ close: [] }>()
const closeBtn = ref<HTMLButtonElement | null>(null)
const showEn = () => props.sub && props.lang !== 'en'
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') emit('close') }
onMounted(() => { document.addEventListener('keydown', onKey); closeBtn.value?.focus() })
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="about-title">
      <header>
        <FexMark :size="44" />
        <h2 id="about-title">{{ t.about.title }}<span v-if="showEn()" class="sub-inline"> ({{ en.about.title }})</span></h2>
        <button ref="closeBtn" class="btn-text close" @click="emit('close')">✕ {{ t.close }}</button>
      </header>
      <p class="intro">{{ t.about.intro }}<span v-if="showEn()" class="sub">{{ en.about.intro }}</span></p>
      <ul>
        <li v-for="(s, i) in t.about.sections" :key="i" :class="{ green: s[0] === '🌱' || s[0] === '🌎' }">
          <span class="icon" aria-hidden="true">{{ s[0] }}</span>
          <div>
            <strong>{{ s[1] }}</strong><span v-if="showEn()" class="sub-inline"> ({{ en.about.sections[i][1] }})</span>
            <p>{{ s[2] }}<span v-if="showEn()" class="sub">{{ en.about.sections[i][2] }}</span></p>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: grid; place-items: center; padding: 16px; z-index: 20; }
.sheet { background: var(--ft-ui-surface); border-radius: 14px; max-width: 520px; width: 100%; max-height: 90vh; overflow-y: auto; padding: 18px 20px; box-shadow: 0 10px 30px rgba(0,0,0,.2); }
header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
h2 { margin: 0; font-size: 20px; flex: 1; }
.close { white-space: nowrap; }
.intro { margin: 0 0 12px; }
ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
li { display: grid; grid-template-columns: 28px 1fr; gap: 8px; padding: 10px 12px; border: 1px solid var(--ft-ui-border); border-radius: 10px; }
li.green { background: var(--ft-ui-success-bg); border-color: #CDE7C6; }
li p { margin: 2px 0 0; font-size: 15px; }
.icon { font-size: 20px; }
</style>
