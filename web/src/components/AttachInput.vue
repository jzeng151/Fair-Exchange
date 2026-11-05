<script setup lang="ts">
// Photo and document notes (#169): like a voice note, the result goes to the message box for the producer
// to review and edit. Nothing reaches FEX until they press Send, so the normal PII and scope checks apply.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ATTACHMENT_TYPES, MAX_ATTACHMENT_BYTES, createAttachmentClient, type AttachmentClient } from '../lib/attachmentClient'
import { LiveError } from '../lib/liveClient'

const props = defineProps<{ apiUrl: string; conversationId: string; producerId: string; passcode: string;
  language: string; disabled: boolean; makeClient?: () => AttachmentClient }>()
const emit = defineEmits<{ description: [text: string] }>()
const copy = {
  en: { attach: '📎 Add a photo or document', reading: 'Reading your file with Claude on Amazon Bedrock…', cancel: 'Cancel',
    review: 'Review and edit the description before sending.', photo: 'Photo', document: 'Document',
    wrongFile: 'Choose a JPG, PNG, WebP or PDF file up to 3.75 MB.', unavailable: 'Photos and documents are not available yet. Please describe it in words.',
    failed: 'The file couldn’t be read. Please try again or type your message.',
    privacy: 'Files are deleted right after they are read. The description is not sent until you press Send.' },
  es: { attach: '📎 Agregar una foto o documento', reading: 'Leyendo su archivo con Claude en Amazon Bedrock…', cancel: 'Cancelar',
    review: 'Revise y edite la descripción antes de enviarla.', photo: 'Foto', document: 'Documento',
    wrongFile: 'Elija un archivo JPG, PNG, WebP o PDF de hasta 3.75 MB.', unavailable: 'Las fotos y documentos aún no están disponibles. Descríbalo con palabras.',
    failed: 'No se pudo leer el archivo. Inténtelo de nuevo o escriba su mensaje.',
    privacy: 'Los archivos se eliminan justo después de leerlos. La descripción no se envía hasta que pulse Enviar.' },
  fr: { attach: '📎 Ajouter une photo ou un document', reading: 'Lecture de votre fichier avec Claude sur Amazon Bedrock…', cancel: 'Annuler',
    review: 'Relisez et modifiez la description avant de l’envoyer.', photo: 'Photo', document: 'Document',
    wrongFile: 'Choisissez un fichier JPG, PNG, WebP ou PDF de 3,75 Mo maximum.', unavailable: 'Les photos et documents ne sont pas encore disponibles. Décrivez-le avec des mots.',
    failed: 'Le fichier n’a pas pu être lu. Réessayez ou écrivez votre message.',
    privacy: 'Les fichiers sont supprimés juste après leur lecture. La description est envoyée uniquement lorsque vous appuyez sur Envoyer.' },
}
const t = computed(() => copy[props.language as keyof typeof copy] ?? copy.en)
const reading = ref(false)
const notice = ref('')
const error = ref(false)
const picker = ref<HTMLInputElement | null>(null)
let generation = 0
let pending: { api: AttachmentClient; id: string } | undefined

function cancel() {
  generation++
  if (pending) void pending.api.cancel(pending.id).catch(() => {})
  pending = undefined
  reading.value = false
}
function fail(message: string) { error.value = true; notice.value = message }

async function chosen(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || props.disabled || reading.value) return
  notice.value = ''; error.value = false
  if (!(ATTACHMENT_TYPES as readonly string[]).includes(file.type) || file.size < 1 || file.size > MAX_ATTACHMENT_BYTES) {
    return fail(t.value.wrongFile)
  }
  const mine = ++generation
  const api = props.makeClient?.() ?? createAttachmentClient({ baseUrl: props.apiUrl, producerId: props.producerId, passcode: props.passcode }, props.conversationId)
  reading.value = true
  let created
  try {
    created = await api.create(file.type)
  } catch (err) {
    if (mine !== generation) return
    reading.value = false
    // API Gateway answers 403/404 for a route that isn't deployed yet.
    return fail(err instanceof LiveError && (err.status === 403 || err.status === 404) ? t.value.unavailable : t.value.failed)
  }
  if (mine !== generation) { void api.cancel(created.attachment_id).catch(() => {}); return }
  pending = { api, id: created.attachment_id }
  try {
    await api.upload(created.upload, file)
    if (mine !== generation) return
    const { description } = await api.read(created.attachment_id)
    if (mine !== generation) return
    pending = undefined
    reading.value = false
    const label = file.type === 'application/pdf' ? t.value.document : t.value.photo
    emit('description', `[${label}: ${description.trim()}]`)
    notice.value = t.value.review
  } catch {
    if (mine !== generation) return
    cancel()
    fail(t.value.failed)
  }
}
watch(() => [props.disabled, props.conversationId, props.producerId, props.passcode], () => cancel())
onBeforeUnmount(cancel)
</script>

<template>
  <section class="attach-input" :aria-label="t.attach">
    <input ref="picker" type="file" class="sr-only" tabindex="-1" :accept="ATTACHMENT_TYPES.join(',')" @change="chosen" />
    <div class="attach-controls">
      <button v-if="!reading" type="button" class="btn-text" data-action="attach" :disabled="disabled" @click="picker?.click()">{{ t.attach }}</button>
      <button v-else type="button" class="btn-text" data-action="cancel-attach" @click="cancel">{{ t.cancel }}</button>
    </div>
    <p class="small" :role="error ? 'alert' : 'status'">{{ reading ? t.reading : notice }}</p>
    <p class="small">{{ t.privacy }}</p>
  </section>
</template>

<style scoped>
.attach-input { border-top: 1px solid var(--ft-ui-border, #dadce0); padding: 8px 0; }
.attach-controls { display: flex; gap: 12px; flex-wrap: wrap; }
p { margin: 4px 0; }
</style>
