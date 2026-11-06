// Listen (#169): POST /conversations/{id}/speech returns Amazon Polly's MP3 as base64 JSON.
import { demoIdentityHeaders, LiveError, type LiveConfig } from './liveClient'

export function createSpeechClient(cfg: LiveConfig, conversationId: string) {
  const fetcher = cfg.fetch ?? fetch
  const url = `${cfg.baseUrl.replace(/\/+$/, '')}/conversations/${encodeURIComponent(conversationId)}/speech`
  return {
    async speak(text: string): Promise<Blob> {
      const res = await fetcher(url, { method: 'POST', headers: { 'content-type': 'application/json',
        ...demoIdentityHeaders(cfg.producerId, cfg.passcode) }, body: JSON.stringify({ text }) })
      if (!res.ok) throw new LiveError(res.status, 'Speech request failed')
      const body = await res.json() as { content_type?: string; audio?: string }
      if (!body.audio) throw new LiveError(500, 'No audio returned')
      const bytes = Uint8Array.from(atob(body.audio), (c) => c.charCodeAt(0))
      return new Blob([bytes], { type: body.content_type ?? 'audio/mpeg' })
    },
  }
}
export type SpeechClient = ReturnType<typeof createSpeechClient>
