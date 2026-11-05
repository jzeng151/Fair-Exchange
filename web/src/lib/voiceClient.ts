import { demoIdentityHeaders, LiveError, type LiveConfig } from './liveClient'
export interface VoiceUpload { voice_id: string; upload: { url: string; fields: Record<string, string> } }
export interface VoiceResult { status: 'pending' | 'done' | 'delivered' | 'failed' | 'cancelled'; transcript?: string; transcript_english?: string }
export function createVoiceClient(cfg: LiveConfig, conversationId: string) {
  const fetcher = cfg.fetch ?? fetch
  const base = `${cfg.baseUrl.replace(/\/+$/, '')}/conversations/${encodeURIComponent(conversationId)}/voice`
  async function request<T>(method: string, suffix = '', body?: unknown, signal?: AbortSignal): Promise<T> {
    const res = await fetcher(base + suffix, { method, signal, headers: { 'content-type': 'application/json',
      ...demoIdentityHeaders(cfg.producerId, cfg.passcode) }, body: body === undefined ? undefined : JSON.stringify(body) })
    if (!res.ok) throw new LiveError(res.status, 'Voice request failed')
    return res.json() as Promise<T>
  }
  return {
    create: (contentType: string) => request<VoiceUpload>('POST', '', { content_type: contentType }),
    async upload(upload: VoiceUpload['upload'], audio: Blob, signal: AbortSignal) {
      const form = new FormData()
      for (const [key, value] of Object.entries(upload.fields)) form.append(key, value)
      form.append('file', audio)
      // S3 receives only the presigned form, never the API's identity/passcode headers.
      const res = await fetcher(upload.url, { method: 'POST', body: form, signal })
      if (!res.ok) throw new LiveError(res.status, 'Voice upload failed')
    },
    start: (id: string, signal?: AbortSignal) => request<VoiceResult>('POST', `/${encodeURIComponent(id)}/transcribe`, {}, signal),
    get: (id: string, signal?: AbortSignal) => request<VoiceResult>('GET', `/${encodeURIComponent(id)}`, undefined, signal),
    cancel: (id: string) => request<VoiceResult>('DELETE', `/${encodeURIComponent(id)}`),
  }
}
export type VoiceClient = ReturnType<typeof createVoiceClient>
