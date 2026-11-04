import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VoiceNoteRecorder } from './voice-capture'

describe('VoiceNoteRecorder resource cleanup', () => {
  let tracks, stream, source, node, ctx, getUserMedia, createObjectURL, revokeObjectURL

  beforeEach(() => {
    vi.useFakeTimers()
    tracks = [{ stop: vi.fn() }, { stop: vi.fn() }]
    stream = { getTracks: () => tracks }
    source = { connect: vi.fn(), disconnect: vi.fn() }
    node = { port: { onmessage: null }, disconnect: vi.fn() }
    ctx = {
      sampleRate: 16000,
      audioWorklet: { addModule: vi.fn().mockResolvedValue(undefined) },
      createMediaStreamSource: vi.fn().mockReturnValue(source),
      close: vi.fn().mockResolvedValue(undefined),
    }
    getUserMedia = vi.fn().mockResolvedValue(stream)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
    vi.stubGlobal('AudioContext', vi.fn(function () { return ctx }))
    vi.stubGlobal('AudioWorkletNode', vi.fn(function () { return node }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ transcript: 'Hola.' }),
    }))
    createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:worklet')
    revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('releases the microphone and context when worklet loading fails', async () => {
    const failure = new Error('CSP blocked the worklet')
    ctx.audioWorklet.addModule.mockRejectedValue(failure)
    const recorder = new VoiceNoteRecorder('/voice')

    await expect(recorder._start()).rejects.toBe(failure)

    for (const track of tracks) expect(track.stop).toHaveBeenCalledOnce()
    expect(ctx.close).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:worklet')
    expect(vi.getTimerCount()).toBe(0)
    await expect(recorder.stop()).rejects.toThrow('never started')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('releases the microphone if constructing the audio context fails', async () => {
    const failure = new Error('AudioContext unavailable')
    AudioContext.mockImplementation(function () { throw failure })

    await expect(new VoiceNoteRecorder('/voice')._start()).rejects.toBe(failure)

    for (const track of tracks) expect(track.stop).toHaveBeenCalledOnce()
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('disconnects partially initialized nodes and leaves no usable recording', async () => {
    const failure = new Error('Cannot connect the source')
    source.connect.mockImplementation(() => { throw failure })
    const recorder = new VoiceNoteRecorder('/voice')

    await expect(recorder._start()).rejects.toBe(failure)

    for (const track of tracks) expect(track.stop).toHaveBeenCalledOnce()
    expect(source.disconnect).toHaveBeenCalledOnce()
    expect(node.disconnect).toHaveBeenCalledOnce()
    expect(node.port.onmessage).toBeNull()
    expect(ctx.close).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:worklet')
    expect(vi.getTimerCount()).toBe(0)
    await expect(recorder.stop()).rejects.toThrow('never started')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('preserves the initialization error if closing the context also fails', async () => {
    const failure = new Error('CSP blocked the worklet')
    ctx.audioWorklet.addModule.mockRejectedValue(failure)
    ctx.close.mockRejectedValue(new Error('Context close failed'))

    await expect(new VoiceNoteRecorder('/voice')._start()).rejects.toBe(failure)

    for (const track of tracks) expect(track.stop).toHaveBeenCalledOnce()
    expect(ctx.close).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:worklet')
  })

  it.each(['manual', 'timeout'])('cleans up on %s stop and uploads only once', async (mode) => {
    const recorder = new VoiceNoteRecorder('/voice')
    recorder.conversationId = 'C-1001'
    await recorder._start()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:worklet')
    node.port.onmessage({ data: new Float32Array([0, 0.5, -0.5]) })

    if (mode === 'timeout') await vi.advanceTimersByTimeAsync(60_000)
    const results = await Promise.all([recorder.stop(), recorder.stop()])

    expect(results).toEqual([{ transcript: 'Hola.' }, { transcript: 'Hola.' }])
    for (const track of tracks) expect(track.stop).toHaveBeenCalledOnce()
    expect(ctx.close).toHaveBeenCalledOnce()
    expect(source.disconnect).toHaveBeenCalledOnce()
    expect(node.disconnect).toHaveBeenCalledOnce()
    expect(node.port.onmessage).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
    expect(fetch).toHaveBeenCalledOnce()
    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body.conversation_id).toBe('C-1001')
    expect(Buffer.from(body.pcm_b64, 'base64')).toHaveLength(6)
  })
})
