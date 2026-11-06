// Listen (#169): one player for the whole chat, so only one item is ever read aloud. Amazon Polly's audio
// comes from the speech route; if that fails, the browser's own voice reads the text instead.
// Each play takes a turn number and stop() moves it on, so a reply that arrives after the producer
// pressed stop, or started another Listen, never starts playing.
import { reactive } from 'vue'

export interface AudioLike {
  play(): Promise<void>
  pause(): void
  onended: (() => void) | null
  onerror: (() => void) | null
}
interface UtteranceLike { lang: string; onend: (() => void) | null; onerror: (() => void) | null }
interface SynthLike { speak(u: never): void; cancel(): void }

const LOCALES: Record<string, string> = { en: 'en-US', es: 'es-US', fr: 'fr-FR' }

export interface ListenPlayerOptions {
  fetchAudio: (text: string) => Promise<Blob>
  makeAudio?: (url: string) => AudioLike
  objectUrl?: (blob: Blob) => string
  revokeUrl?: (url: string) => void
  synth?: SynthLike | null
  Utterance?: new (text: string) => UtteranceLike
}

export function createListenPlayer(opts: ListenPlayerOptions) {
  const browser = typeof window !== 'undefined'
  const makeAudio = opts.makeAudio ?? ((url: string) => new Audio(url) as AudioLike)
  const objectUrl = opts.objectUrl ?? ((b: Blob) => URL.createObjectURL(b))
  const revokeUrl = opts.revokeUrl ?? ((u: string) => { try { URL.revokeObjectURL(u) } catch { /* not a blob URL */ } })
  const synth = opts.synth !== undefined ? opts.synth : (browser && 'speechSynthesis' in window ? window.speechSynthesis : null)
  const Utterance = opts.Utterance ?? (browser && 'SpeechSynthesisUtterance' in window ? window.SpeechSynthesisUtterance : undefined)

  const state = reactive({ playing: null as string | null, unavailable: false })
  let turn = 0
  let audio: AudioLike | null = null

  function stop() {
    turn++
    audio?.pause()
    audio = null
    synth?.cancel()
    state.playing = null
  }

  async function play(key: string, text: string, language: string) {
    stop()
    const mine = turn
    state.playing = key
    state.unavailable = false
    const finished = () => { if (mine === turn) state.playing = null }
    try {
      const blob = await opts.fetchAudio(text)
      if (mine !== turn) return
      const url = objectUrl(blob)
      const a = makeAudio(url)
      audio = a
      a.onended = a.onerror = () => { revokeUrl(url); finished() }
      await a.play()
      return
    } catch {
      if (mine !== turn) return
    }
    if (!synth || !Utterance) {
      state.playing = null
      state.unavailable = true
      return
    }
    const u = new Utterance(text)
    u.lang = LOCALES[language] ?? 'en-US'
    u.onend = u.onerror = finished
    synth.speak(u as never)
  }

  /** The Listen button: start this item, or stop it if it is the one playing. */
  function toggle(key: string, text: string, language: string) {
    if (state.playing === key) stop()
    else void play(key, text, language)
  }

  return { state, play, stop, toggle }
}
export type ListenPlayer = ReturnType<typeof createListenPlayer>
