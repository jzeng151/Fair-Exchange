<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { createVoiceClient, type VoiceClient } from '../lib/voiceClient'
import { recordAudio, type Recording } from '../lib/voiceRecorder'
const props = defineProps<{ apiUrl: string; conversationId: string; producerId: string; passcode: string;
  language: string; disabled: boolean; makeClient?: () => VoiceClient; capture?: typeof recordAudio }>()
const emit = defineEmits<{ transcript: [text: string, english?: string] }>()
const copy = {
  en: { record: 'Record voice note', requesting: 'Allow microphone access to record.', recording: 'Recording. Maximum two minutes.',
    stop: 'Stop and transcribe', cancel: 'Cancel voice note', waiting: 'Transcribing… You can still type.',
    review: 'Review and edit the transcript before sending.', failed: 'Voice input failed. Please try again or type your message.',
    privacy: 'Audio is deleted after transcription. The transcript is not sent until you press Send.' },
  es: { record: 'Grabar nota de voz', requesting: 'Permite el acceso al micrófono para grabar.', recording: 'Grabando. Máximo dos minutos.',
    stop: 'Detener y transcribir', cancel: 'Cancelar nota de voz', waiting: 'Transcribiendo… Puedes seguir escribiendo.',
    review: 'Revisa y edita la transcripción antes de enviarla.', failed: 'No se pudo transcribir. Inténtalo de nuevo o escribe tu mensaje.',
    privacy: 'El audio se elimina después de la transcripción. El texto no se envía hasta que pulses Enviar.' },
  fr: { record: 'Enregistrer un message vocal', requesting: 'Autorisez le microphone pour enregistrer.', recording: 'Enregistrement. Deux minutes maximum.',
    stop: 'Arrêter et transcrire', cancel: 'Annuler le message vocal', waiting: 'Transcription… Vous pouvez continuer à écrire.',
    review: 'Relisez et modifiez la transcription avant de l’envoyer.', failed: 'Échec de la saisie vocale. Réessayez ou écrivez votre message.',
    privacy: 'L’audio est supprimé après la transcription. Le texte est envoyé uniquement lorsque vous appuyez sur Envoyer.' },
}
const t = computed(() => copy[props.language as keyof typeof copy] ?? copy.en)
const phase = ref<'idle' | 'requesting' | 'recording' | 'waiting'>('idle')
const notice = ref(''); const error = ref(false)
let generation = 0; let recording: Recording | undefined; let controller: AbortController | undefined
let pollTimer: ReturnType<typeof setTimeout> | undefined
let voiceId: string | undefined; let api: VoiceClient | undefined
const delay = (signal: AbortSignal) => new Promise<void>(resolve => {
  const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }
  const timer = setTimeout(done, 2000); signal.addEventListener('abort', done, { once: true })
  if (signal.aborted) done()
})
function cancel() {
  generation++; clearTimeout(pollTimer); recording?.cancel(); recording = undefined; controller?.abort()
  const old = voiceId; voiceId = undefined
  if (old && api) void api.cancel(old).catch(() => {})
  phase.value = 'idle'; notice.value = ''; error.value = false
}
async function start() {
  if (props.disabled || phase.value !== 'idle') return
  const mine = ++generation; notice.value = ''; error.value = false; phase.value = 'requesting'
  const service = props.makeClient?.() ?? createVoiceClient({ baseUrl: props.apiUrl, producerId: props.producerId, passcode: props.passcode }, props.conversationId)
  api = service
  try {
    const capture = await (props.capture ?? recordAudio)()
    if (mine !== generation) { capture.cancel(); return }
    recording = capture; phase.value = 'recording'
    // Automatic two-minute stop follows exactly the same upload path as clicking Stop.
    const audio = await capture.result
    if (mine !== generation) return
    recording = undefined; phase.value = 'waiting'
    controller = new AbortController(); const signal = controller.signal
    const created = await service.create(audio.type)
    if (mine !== generation) { await service.cancel(created.voice_id); return }
    voiceId = created.voice_id
    await service.upload(created.upload, audio, signal)
    if (mine !== generation) return
    pollTimer = setTimeout(() => controller?.abort(), 90_000)
    await service.start(created.voice_id, signal)
    const deadline = Date.now() + 90_000
    while (mine === generation && Date.now() < deadline) {
      await delay(signal)
      if (mine !== generation) return
      if (signal.aborted) throw new Error('Transcription timed out')
      const result = await service.get(created.voice_id, signal)
      if (mine !== generation) return
      if (result.status === 'done' && result.transcript) {
        emit('transcript', result.transcript, result.transcript_english)
        clearTimeout(pollTimer); voiceId = undefined; phase.value = 'idle'; notice.value = t.value.review; return
      }
      if (result.status !== 'pending') throw new Error('Transcription unavailable')
    }
    if (mine === generation) throw new Error('Transcription timed out')
  } catch {
    if (mine !== generation) return
    cancel(); error.value = true; notice.value = t.value.failed
  }
}
function stop() { void recording?.stop().catch(() => {}) }
watch(() => [props.disabled, props.conversationId, props.producerId, props.passcode], () => cancel())
onBeforeUnmount(cancel)
</script>
<template>
  <section class="voice-input" :aria-label="t.record">
    <div class="voice-controls">
      <button v-if="phase === 'idle'" type="button" class="btn-text" :disabled="disabled" @click="start">{{ t.record }}</button>
      <button v-if="phase === 'recording'" type="button" class="btn-primary" @click="stop">{{ t.stop }}</button>
      <button v-if="phase !== 'idle'" type="button" class="btn-text" @click="cancel">{{ t.cancel }}</button>
    </div>
    <p class="small" :role="error ? 'alert' : 'status'">{{ phase === 'idle' ? notice : t[phase] }}</p>
    <p class="small">{{ t.privacy }}</p>
  </section>
</template>
<style scoped>
.voice-input { border-top: 1px solid var(--ft-ui-border, #dadce0); padding: 8px 0; }
.voice-controls { display: flex; gap: 12px; flex-wrap: wrap; } p { margin: 4px 0; }
</style>
