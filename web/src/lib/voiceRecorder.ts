export interface Recording { stop: () => Promise<Blob>; cancel: () => void; result: Promise<Blob> }
export const MAX_AUDIO_BYTES = 5 * 1024 * 1024
/** Mic access occurs only on the producer's click. All exit paths release the tracks. */
export async function recordAudio(): Promise<Recording> {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') throw new Error('Recording unavailable')
  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported(t))
  if (!mime) throw new Error('Recording format unavailable')
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  let recorder: MediaRecorder
  try { recorder = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 64000 }) }
  catch (e) { stream.getTracks().forEach(t => t.stop()); throw e }
  const chunks: Blob[] = []; let bytes = 0; let cancelled = false; let failed = false
  let timer: ReturnType<typeof setTimeout>
  const release = () => { clearTimeout(timer); stream.getTracks().forEach(t => t.stop()) }
  const result = new Promise<Blob>((resolve, reject) => {
    recorder.ondataavailable = e => {
      bytes += e.data.size
      if (bytes > MAX_AUDIO_BYTES) { failed = true; if (recorder.state !== 'inactive') recorder.stop() }
      else chunks.push(e.data)
    }
    recorder.onerror = () => { failed = true; release(); reject(new Error('Recording failed')) }
    recorder.onstop = () => {
      release()
      if (cancelled || failed) reject(new Error('Recording cancelled or too large'))
      else resolve(new Blob(chunks, { type: mime.startsWith('audio/mp4') ? 'audio/mp4' : 'audio/webm' }))
    }
  })
  // A permission or recorder error may precede the caller awaiting stop().
  void result.catch(() => {})
  try { recorder.start(250); timer = setTimeout(() => { if (recorder.state !== 'inactive') recorder.stop() }, 120_000) }
  catch (e) { release(); throw e }
  return { result, stop: () => { if (recorder.state !== 'inactive') recorder.stop(); return result },
    cancel: () => { cancelled = true; if (recorder.state !== 'inactive') recorder.stop(); release() } }
}
