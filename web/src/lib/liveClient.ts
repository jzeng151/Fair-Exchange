// Live mode (#116): the web client for the real chat API. Routes and stream format: docs/specs/25-chat-endpoint.md.
//   POST /conversations                  -> NDJSON stream (first event: {type: 'conversation', conversationId})
//   POST /conversations/{id}/messages    {text}           -> NDJSON stream
//   POST /conversations/{id}/actions     {action, args}   -> NDJSON stream
//   GET  /conversations/{id}             -> resume view (step, language, allowed actions, answer, history)
// Event shapes are the generated shared contract (api/src/types/conversation-contract.ts); never hand-written.
import type { Event, ResumeResponse } from '../../../api/src/types/conversation-contract'

export type { Event, ResumeResponse }
export type ActionName = ResumeResponse['allowed'][number]
export type StreamEvent = Event | { type: 'conversation'; conversationId: string }

/** A failed request. `status` is the HTTP status, or 0 when the API could not be reached. */
export class LiveError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
    this.name = 'LiveError'
  }
}

/**
 * LOCAL ONLY: who the caller is. The local chat API (api/src/local/server.ts) reads this header as a stand-in
 * for sign-in. How callers sign in when deployed is "Not decided" (docs/specs/11-identity.md), so this is the one
 * place to change once it is.
 */
export function demoIdentityHeaders(producerId: string): Record<string, string> {
  return { 'x-demo-producer-id': producerId }
}

/** Parse a newline-delimited JSON body as it arrives, one object per line. */
export async function* readNdjson(body: ReadableStream<Uint8Array>): AsyncGenerator<unknown> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = done ? '' : lines.pop() ?? ''
      for (const line of lines) if (line.trim()) yield JSON.parse(line)
      if (done) return
    }
  } finally {
    reader.releaseLock()
  }
}

export interface LiveConfig {
  baseUrl: string
  producerId: string
  fetch?: typeof fetch
}

export function createLiveClient(cfg: LiveConfig) {
  const base = cfg.baseUrl.replace(/\/+$/, '')
  const doFetch = cfg.fetch ?? ((...a: Parameters<typeof fetch>) => fetch(...a))

  async function request(method: 'GET' | 'POST', path: string, body?: unknown): Promise<Response> {
    let res: Response
    try {
      res = await doFetch(`${base}${path}`, {
        method,
        headers: { ...(body === undefined ? {} : { 'content-type': 'application/json' }), ...demoIdentityHeaders(cfg.producerId) },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch {
      throw new LiveError(0, `Can't reach the chat API at ${base}`)
    }
    if (!res.ok) {
      let message = `Request failed (${res.status})`
      try {
        const parsed = (await res.json()) as { message?: unknown }
        if (typeof parsed.message === 'string') message = parsed.message
      } catch { /* keep the generic message */ }
      throw new LiveError(res.status, message)
    }
    return res
  }

  async function* stream(path: string, body: unknown): AsyncGenerator<StreamEvent> {
    const res = await request('POST', path, body)
    if (!res.body) throw new LiveError(res.status, 'The chat API returned an empty stream')
    for await (const event of readNdjson(res.body)) yield event as StreamEvent
  }

  const at = (id: string) => `/conversations/${encodeURIComponent(id)}`
  return {
    start: () => stream('/conversations', {}),
    message: (id: string, text: string) => stream(`${at(id)}/messages`, { text }),
    action: (id: string, action: ActionName, args: Record<string, unknown> = {}) => stream(`${at(id)}/actions`, { action, args }),
    resume: async (id: string): Promise<ResumeResponse> => (await request('GET', at(id))).json() as Promise<ResumeResponse>,
  }
}

export type LiveClient = ReturnType<typeof createLiveClient>
