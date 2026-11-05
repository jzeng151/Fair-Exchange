<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { liveProducers } from '../data/liveProducers'
import type { Lang } from '../data/i18n'
import { recordApi } from '../lib/recordApi'
import type { YourRecordRow } from '../lib/yourRecord'
import YourRecordView from './YourRecordView.vue'
const props = defineProps<{ apiUrl: string }>()
const producer = ref(liveProducers[0]?.id ?? '')
const passcode = ref('')
const rows = ref<YourRecordRow[]>([])
const signedIn = ref(false)
const busy = ref(false)
const error = ref('')
const lang = computed<Lang>(() => {
  const language = liveProducers.find((p) => p.id === producer.value)?.language
  return language === 'es' || language === 'fr' ? language : 'en'
})
watch([producer, passcode], () => { signedIn.value = false; rows.value = []; error.value = '' })
async function refresh() {
  busy.value = true; error.value = ''; signedIn.value = false; rows.value = []
  try {
    const api = recordApi(props.apiUrl, { 'x-demo-passcode': passcode.value, 'x-demo-producer-id': producer.value })
    const identity = await api.identity()
    if (!identity.roles.includes('producer')) throw new Error('A producer sign-in is required.')
    rows.value = await api.mine(); signedIn.value = true
  } catch (e) { error.value = e instanceof Error ? e.message : 'Unable to load records.' }
  finally { busy.value = false }
}
defineExpose({ refresh: () => { if (signedIn.value) void refresh() } })
</script>
<template>
  <section>
    <form class="panel record-signin" @submit.prevent="refresh">
      <h1>Your saved records</h1>
      <p>Sign in with the same scenario and demo passcode used in Live FEX.</p>
      <label>Demo scenario<select v-model="producer" :disabled="busy"><option v-for="p in liveProducers" :key="p.scenarioId" :value="p.id">{{ p.title }}</option></select></label>
      <label>Demo passcode<input v-model="passcode" type="password" autocomplete="off" required :disabled="busy" /></label>
      <button class="btn-primary" :disabled="busy">{{ busy ? 'Loading…' : 'Load my records' }}</button>
      <p v-if="error" role="alert">{{ error }}</p>
    </form>
    <YourRecordView v-if="signedIn" :producer-id="producer" :lang="lang" :live-rows="rows" />
  </section>
</template>
<style scoped>
.record-signin { display: grid; gap: 12px; max-width: 48rem; margin: 0 auto 20px; }
label { display: grid; gap: 6px; } input, select { padding: 10px; max-width: 100%; min-width: 0; }
</style>
