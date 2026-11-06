// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AttachInput from './AttachInput.vue'
import { LiveError } from '../lib/liveClient'
import type { AttachmentClient } from '../lib/attachmentClient'

function setup(language = 'es', overrides: Partial<AttachmentClient> = {}) {
  const service: AttachmentClient = {
    create: vi.fn(async () => ({ attachment_id: 'a-1', upload: { url: 'https://s3.test', fields: {} } })),
    upload: vi.fn(async () => {}),
    read: vi.fn(async () => ({ description: 'Hojas secas en las plantas de café.' })),
    cancel: vi.fn(async () => ({ status: 'deleted' })),
    ...overrides,
  }
  const w = mount(AttachInput, { props: { apiUrl: 'https://api.test', conversationId: 'c', producerId: 'p', passcode: 'pc',
    language, disabled: false, makeClient: () => service } })
  return { w, service }
}
async function pick(w: ReturnType<typeof mount>, file: File) {
  const input = w.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await flushPromises()
}
const photo = (size = 10, type = 'image/jpeg') => new File([new Uint8Array(size)], 'campo.jpg', { type })

describe('attach input (#169)', () => {
  it("reads the photo and hands back a labelled description for the message box, in the conversation's language", async () => {
    const { w, service } = setup('es')
    await pick(w, photo())
    expect(service.create).toHaveBeenCalledWith('image/jpeg')
    expect(service.upload).toHaveBeenCalled()
    expect(service.read).toHaveBeenCalledWith('a-1')
    expect(w.emitted('description')).toEqual([['[Foto: Hojas secas en las plantas de café.]']])
    expect(w.get('[role="status"]').text()).toContain('Revise')
  })

  it('labels a PDF as a document', async () => {
    const { w } = setup('en')
    await pick(w, new File(['%PDF'], 'informe.pdf', { type: 'application/pdf' }))
    expect(w.emitted('description')).toEqual([['[Document: Hojas secas en las plantas de café.]']])
  })

  it('refuses a file that is too big or of another type before uploading anything', async () => {
    const { w, service } = setup('en')
    await pick(w, photo(3_932_161))
    await pick(w, photo(10, 'image/gif'))
    expect(service.create).not.toHaveBeenCalled()
    expect(w.emitted('description')).toBeUndefined()
    expect(w.get('[role="alert"]').text()).toContain('JPG, PNG, WebP or PDF')
  })

  it('says the feature is not available yet when the API has no attachment route', async () => {
    const { w } = setup('en', { create: vi.fn(async () => { throw new LiveError(403, 'Missing Authentication Token') }) })
    await pick(w, photo())
    expect(w.get('[role="alert"]').text()).toContain('not available yet')
  })

  it('deletes the upload and offers typing instead when reading fails', async () => {
    const { w, service } = setup('en', { read: vi.fn(async () => { throw new LiveError(500, 'x') }) })
    await pick(w, photo())
    expect(service.cancel).toHaveBeenCalledWith('a-1')
    expect(w.emitted('description')).toBeUndefined()
    expect(w.get('[role="alert"]').text()).toContain('type')
  })

  it('deletes the file again once an upload cancelled mid-flight finishes, so S3 is not left holding it', async () => {
    let finishUpload!: () => void
    const { w, service } = setup('en', { upload: vi.fn(() => new Promise<void>((r) => { finishUpload = r })) })
    await pick(w, photo())
    await w.get('[data-action="cancel-attach"]').trigger('click')
    expect(service.cancel).toHaveBeenCalledTimes(1) // at once, in case the upload already landed
    finishUpload()
    await flushPromises()
    expect(service.cancel).toHaveBeenCalledTimes(2) // and again, because the upload recreated the object
    expect(service.cancel).toHaveBeenLastCalledWith('a-1')
    expect(service.read).not.toHaveBeenCalled()
    expect(w.emitted('description')).toBeUndefined()
  })
})
