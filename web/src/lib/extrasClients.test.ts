import { describe, expect, it, vi } from 'vitest'
import { createSpeechClient } from './speechClient'
import { createAttachmentClient } from './attachmentClient'
import { LiveError } from './liveClient'

const cfg = (fetch: typeof globalThis.fetch) => ({ baseUrl: 'https://api.test/v1/', producerId: 'P1', passcode: 'pc', fetch })
const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })

describe('speech client (#169)', () => {
  it("posts only the text with the producer's identity and returns Polly's MP3", async () => {
    const fetch = vi.fn(async () => ok({ content_type: 'audio/mpeg', audio: btoa('ID3mp3') }))
    const blob = await createSpeechClient(cfg(fetch), 'c-1').speak('Hola')
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('https://api.test/v1/conversations/c-1/speech')
    expect(JSON.parse(init.body as string)).toEqual({ text: 'Hola' })
    expect((init.headers as Record<string, string>)['x-demo-producer-id']).toBe('P1')
    expect(blob.type).toBe('audio/mpeg')
    expect(await blob.text()).toBe('ID3mp3')
  })

  it('throws a LiveError with the status when the route fails', async () => {
    const fetch = vi.fn(async () => new Response('{}', { status: 403 }))
    await expect(createSpeechClient(cfg(fetch), 'c-1').speak('Hola')).rejects.toMatchObject({ status: 403 })
  })
})

describe('attachment client (#169)', () => {
  it('creates an upload, uploads the file to S3 with only the form fields, then reads it', async () => {
    const fetch = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith('/attachments')) return ok({ attachment_id: 'a-1', upload: { url: 'https://s3.test', fields: { key: 'k' } } })
      if (url === 'https://s3.test') return new Response(null, { status: 204 })
      return ok({ description: 'Hojas secas en las plantas de café.' })
    })
    const client = createAttachmentClient(cfg(fetch as never), 'c-1')
    const file = new File(['img'], 'campo.jpg', { type: 'image/jpeg' })
    const created = await client.create(file.type)
    await client.upload(created.upload, file)
    const read = await client.read(created.attachment_id)
    expect(read.description).toBe('Hojas secas en las plantas de café.')
    const calls = fetch.mock.calls as unknown as [string, RequestInit][]
    expect(calls.map(([u, i]) => `${i.method} ${u}`)).toEqual([
      'POST https://api.test/v1/conversations/c-1/attachments',
      'POST https://s3.test',
      'POST https://api.test/v1/conversations/c-1/attachments/a-1/read',
    ])
    expect(JSON.parse(calls[0]![1].body as string)).toEqual({ content_type: 'image/jpeg' })
    expect(calls[1]![1].headers).toBeUndefined() // S3 never sees the API's identity or passcode headers
  })

  it('cancels with DELETE', async () => {
    const fetch = vi.fn(async () => ok({ status: 'deleted' }))
    await createAttachmentClient(cfg(fetch), 'c-1').cancel('a-1')
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(`${init.method} ${url}`).toBe('DELETE https://api.test/v1/conversations/c-1/attachments/a-1')
  })

  it('reports a missing route as a LiveError, so the chat can say "not available yet"', async () => {
    const fetch = vi.fn(async () => new Response('{"message":"Missing Authentication Token"}', { status: 403 }))
    const err = await createAttachmentClient(cfg(fetch), 'c-1').create('image/png').catch((e) => e)
    expect(err).toBeInstanceOf(LiveError)
    expect(err.status).toBe(403)
  })
})
