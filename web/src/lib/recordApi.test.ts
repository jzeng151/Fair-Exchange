import { describe, expect, it, vi } from 'vitest'
import { recordApi } from './recordApi'
describe('deployed record API client', () => {
  it('preserves the loaded version on corrections and surfaces conflicts', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 409 }))
    const api = recordApi('https://api.example.test/v1/', { 'x-demo-reviewer-passcode': 'test' }, fetcher)
    await expect(api.patch('record-id', { version: 3, reviewer_tags: ['water'] })).rejects.toMatchObject({ status: 409 })
    expect(fetcher).toHaveBeenCalledWith('https://api.example.test/v1/records/record-id', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ version: 3, reviewer_tags: ['water'] }) }))
  })
  it('maps the producer projection without reading browser demo records', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ records: [{ record_id: 'r', status: 'declined', closed_at: '2026-11-04T12:00:00Z' }] })))
    expect(await recordApi('https://api.example.test', { 'x-demo-passcode': 'test', 'x-demo-producer-id': 'P-001' }, fetcher).mine())
      .toEqual([{ recordId: 'r', status: 'declined', closedAt: '2026-11-04T12:00:00Z' }])
  })
})
