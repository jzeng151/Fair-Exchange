import { describe, expect, it } from 'vitest'
import { createLiveClient, demoIdentityHeaders, LiveError, readNdjson } from './liveClient'

const enc = new TextEncoder()

/** A response body that arrives in the given chunks, like a real network stream. */
function chunked(chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(c) {
      for (const s of chunks) c.enqueue(enc.encode(s))
      c.close()
    },
  })
}

interface Call { url: string; init: RequestInit }
function fakeFetch(respond: (call: Call) => Response) {
  const calls: Call[] = []
  const fn = (async (url: string, init: RequestInit) => {
    const call = { url: String(url), init }
    calls.push(call)
    return respond(call)
  }) as unknown as typeof fetch
  return { fn, calls }
}
const ndjson = (lines: object[], status = 200) =>
  new Response(chunked([lines.map((l) => JSON.stringify(l)).join('\n') + '\n']),
    { status, headers: { 'content-type': 'application/x-ndjson' } })

async function all<T>(gen: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = []
  for await (const x of gen) out.push(x)
  return out
}

describe('readNdjson', () => {
  it('yields one event per line, even when a line is split across chunks', async () => {
    const events = await all(readNdjson(chunked(['{"type":"te', 'xt","seq":1,"text":"Hola"}\n{"type":', '"done","seq":2}\n'])))
    expect(events).toEqual([{ type: 'text', seq: 1, text: 'Hola' }, { type: 'done', seq: 2 }])
  })

  it('keeps multi-byte characters intact across a chunk boundary', async () => {
    const bytes = enc.encode('{"type":"text","text":"¿Qué?"}\n')
    const cut = bytes.indexOf(0xbf) // inside the two-byte "¿"
    const body = new ReadableStream<Uint8Array>({
      start(c) { c.enqueue(bytes.slice(0, cut)); c.enqueue(bytes.slice(cut)); c.close() },
    })
    expect(await all(readNdjson(body))).toEqual([{ type: 'text', text: '¿Qué?' }])
  })

  it('reads a last line with no trailing newline and skips blank lines', async () => {
    expect(await all(readNdjson(chunked(['\n{"type":"done"}'])))).toEqual([{ type: 'done' }])
  })
})

describe('createLiveClient', () => {
  const base = 'http://127.0.0.1:3000/'

  it('starts a conversation with POST /conversations and streams its events', async () => {
    const f = fakeFetch(() => ndjson([{ type: 'conversation', conversationId: 'c-1' }, { type: 'done', seq: 1 }]))
    const client = createLiveClient({ baseUrl: base, producerId: 'P1', fetch: f.fn })
    expect(await all(client.start())).toEqual([{ type: 'conversation', conversationId: 'c-1' }, { type: 'done', seq: 1 }])
    expect(f.calls[0]!.url).toBe('http://127.0.0.1:3000/conversations')
    expect(f.calls[0]!.init.method).toBe('POST')
    expect(JSON.parse(String(f.calls[0]!.init.body))).toEqual({})
  })

  it('sends messages and actions to the agreed routes and bodies (#25)', async () => {
    const f = fakeFetch(() => ndjson([{ type: 'done', seq: 1 }]))
    const client = createLiveClient({ baseUrl: base, producerId: 'P1', fetch: f.fn })
    await all(client.message('c-1', 'La lluvia bajó'))
    await all(client.action('c-1', 'set_consent', { scope: 'internal' }))
    await all(client.action('c-1', 'confirm_playback'))
    expect(f.calls.map((c) => [c.url, JSON.parse(String(c.init.body))])).toEqual([
      ['http://127.0.0.1:3000/conversations/c-1/messages', { text: 'La lluvia bajó' }],
      ['http://127.0.0.1:3000/conversations/c-1/actions', { action: 'set_consent', args: { scope: 'internal' } }],
      ['http://127.0.0.1:3000/conversations/c-1/actions', { action: 'confirm_playback', args: {} }],
    ])
  })

  it('never puts the producer ID in a body or URL, only in the identity headers', async () => {
    const f = fakeFetch(() => ndjson([{ type: 'done', seq: 1 }]))
    const client = createLiveClient({ baseUrl: base, producerId: 'SECRET-ID', fetch: f.fn })
    await all(client.start())
    await all(client.message('c-1', 'hi'))
    for (const c of f.calls) {
      expect(c.url).not.toContain('SECRET-ID')
      expect(String(c.init.body)).not.toContain('SECRET-ID')
      expect((c.init.headers as Record<string, string>)['x-demo-producer-id']).toBe('SECRET-ID')
    }
  })

  it('reads the resume view with GET /conversations/{id}', async () => {
    const view = { step: 'consent', language: 'es', allowed: ['set_consent'], answer: null, history: [] }
    const f = fakeFetch(() => new Response(JSON.stringify(view), { status: 200, headers: { 'content-type': 'application/json' } }))
    const client = createLiveClient({ baseUrl: base, producerId: 'P1', fetch: f.fn })
    expect(await client.resume('c 1')).toEqual(view)
    expect(f.calls[0]!.url).toBe('http://127.0.0.1:3000/conversations/c%201')
    expect(f.calls[0]!.init.method).toBe('GET')
  })

  it('turns a non-2xx reply into a LiveError with the status and the API message', async () => {
    const f = fakeFetch(() => new Response(JSON.stringify({ message: 'A turn is in progress' }), { status: 409 }))
    const client = createLiveClient({ baseUrl: base, producerId: 'P1', fetch: f.fn })
    const err = await all(client.message('c-1', 'hi')).catch((e) => e)
    expect(err).toBeInstanceOf(LiveError)
    expect(err.status).toBe(409)
    expect(err.message).toBe('A turn is in progress')
  })

  it('reports an unreachable API as a LiveError with status 0', async () => {
    const fn = (async () => { throw new TypeError('Failed to fetch') }) as unknown as typeof fetch
    const err = await all(createLiveClient({ baseUrl: base, producerId: 'P1', fetch: fn }).start()).catch((e) => e)
    expect(err).toBeInstanceOf(LiveError)
    expect(err.status).toBe(0)
  })
})

describe('demoIdentityHeaders', () => {
  it('sends the chosen producer, and the demo passcode when one is entered (#11 stand-in)', () => {
    expect(demoIdentityHeaders('P1')).toEqual({ 'x-demo-producer-id': 'P1' })
    expect(demoIdentityHeaders('P1', 'pass')).toEqual({ 'x-demo-producer-id': 'P1', 'x-demo-passcode': 'pass' })
  })
})
