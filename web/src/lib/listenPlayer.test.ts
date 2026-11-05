import { describe, expect, it, vi } from 'vitest'
import { createListenPlayer, type AudioLike } from './listenPlayer'

function fakeAudio() {
  const made: (AudioLike & { url: string; playing: boolean })[] = []
  const makeAudio = (url: string) => {
    const a = { url, playing: false, onended: null as (() => void) | null, onerror: null as (() => void) | null,
      play: vi.fn(async () => { a.playing = true }), pause: vi.fn(() => { a.playing = false }) }
    made.push(a)
    return a
  }
  return { made, makeAudio }
}
function fakeSynth() {
  const spoken: { text: string; lang: string }[] = []
  class Utterance { lang = ''; onend: (() => void) | null = null; onerror: (() => void) | null = null; constructor(public text: string) {} }
  const synth = { speak: vi.fn((u: Utterance) => { spoken.push({ text: u.text, lang: u.lang }) }), cancel: vi.fn() }
  return { spoken, synth, Utterance }
}
const mp3 = () => new Blob(['mp3'], { type: 'audio/mpeg' })

describe('listen player (#169)', () => {
  it('plays the audio from Amazon Polly and marks that item as playing until it ends', async () => {
    const audio = fakeAudio()
    const p = createListenPlayer({ fetchAudio: async () => mp3(), makeAudio: audio.makeAudio, objectUrl: () => 'blob:1' })
    await p.play('a', 'Hola', 'es')
    expect(audio.made).toHaveLength(1)
    expect(audio.made[0]!.playing).toBe(true)
    expect(p.state.playing).toBe('a')
    audio.made[0]!.onended!()
    expect(p.state.playing).toBeNull()
  })

  it('falls back to the browser voice in the conversation language when Polly fails', async () => {
    const s = fakeSynth()
    const p = createListenPlayer({ fetchAudio: async () => { throw new Error('403') }, synth: s.synth, Utterance: s.Utterance as never })
    await p.play('a', 'Bonjour', 'fr')
    expect(s.spoken).toEqual([{ text: 'Bonjour', lang: 'fr-FR' }])
  })

  it('says listening is unavailable when neither Polly nor a browser voice works', async () => {
    const p = createListenPlayer({ fetchAudio: async () => { throw new Error('500') }, synth: null })
    await p.play('a', 'Hello', 'en')
    expect(p.state.playing).toBeNull()
    expect(p.state.unavailable).toBe(true)
  })

  it('never plays a reply that arrives after another Listen started, or after stop', async () => {
    const audio = fakeAudio()
    const pending: ((b: Blob) => void)[] = []
    const p = createListenPlayer({ fetchAudio: () => new Promise<Blob>((r) => pending.push(r)), makeAudio: audio.makeAudio, objectUrl: () => 'blob:x' })
    const first = p.play('a', 'uno', 'es')
    const second = p.play('b', 'dos', 'es')
    pending[1]!(mp3()); await second
    pending[0]!(mp3()); await first
    expect(audio.made).toHaveLength(1)
    expect(p.state.playing).toBe('b')
    const third = p.play('c', 'tres', 'es')
    p.stop()
    pending[2]!(mp3()); await third
    expect(audio.made).toHaveLength(1)
    expect(p.state.playing).toBeNull()
  })

  it('stopping pauses the audio and cancels the browser voice', async () => {
    const audio = fakeAudio(); const s = fakeSynth()
    const p = createListenPlayer({ fetchAudio: async () => mp3(), makeAudio: audio.makeAudio, objectUrl: () => 'blob:1', synth: s.synth })
    await p.play('a', 'Hola', 'es')
    p.stop()
    expect(audio.made[0]!.playing).toBe(false)
    expect(s.synth.cancel).toHaveBeenCalled()
    expect(p.state.playing).toBeNull()
  })
})
