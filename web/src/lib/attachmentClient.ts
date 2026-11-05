// Photo and document notes (#169): create an upload, send the file straight to S3 with the presigned form,
// then ask the API to read it with Claude on Bedrock. The file is deleted by the API after one read.
import { demoIdentityHeaders, LiveError, type LiveConfig } from './liveClient'

export const ATTACHMENT_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'] as const
export const MAX_ATTACHMENT_BYTES = 3_932_160 // 3.75 MB, Bedrock's image limit
export interface AttachmentUpload { attachment_id: string; upload: { url: string; fields: Record<string, string> } }

export function createAttachmentClient(cfg: LiveConfig, conversationId: string) {
  const fetcher = cfg.fetch ?? fetch
  const base = `${cfg.baseUrl.replace(/\/+$/, '')}/conversations/${encodeURIComponent(conversationId)}/attachments`
  async function request<T>(method: string, suffix = '', body?: unknown): Promise<T> {
    const res = await fetcher(base + suffix, { method, headers: { 'content-type': 'application/json',
      ...demoIdentityHeaders(cfg.producerId, cfg.passcode) }, body: body === undefined ? undefined : JSON.stringify(body) })
    if (!res.ok) throw new LiveError(res.status, 'Attachment request failed')
    return res.json() as Promise<T>
  }
  return {
    create: (contentType: string) => request<AttachmentUpload>('POST', '', { content_type: contentType }),
    async upload(upload: AttachmentUpload['upload'], file: Blob) {
      const form = new FormData()
      for (const [key, value] of Object.entries(upload.fields)) form.append(key, value)
      form.append('file', file)
      // S3 receives only the presigned form, never the API's identity/passcode headers.
      const res = await fetcher(upload.url, { method: 'POST', body: form })
      if (!res.ok) throw new LiveError(res.status, 'Attachment upload failed')
    },
    read: (id: string) => request<{ description: string }>('POST', `/${encodeURIComponent(id)}/read`, {}),
    cancel: (id: string) => request<{ status: string }>('DELETE', `/${encodeURIComponent(id)}`),
  }
}
export type AttachmentClient = ReturnType<typeof createAttachmentClient>
