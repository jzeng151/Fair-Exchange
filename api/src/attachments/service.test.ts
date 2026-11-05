import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mockClient } from 'aws-sdk-client-mock';
import { DynamoDBClient, GetItemCommand } from '@aws-sdk/client-dynamodb';
import { S3Client, DeleteObjectCommand, GetObjectCommand, HeadObjectCommand } from '@aws-sdk/client-s3';
import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { marshall } from '@aws-sdk/util-dynamodb';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { attachmentsRoute, MAX_ATTACHMENT_BYTES, type AttachmentDeps } from './service.js';
const db = mockClient(DynamoDBClient), s3 = mockClient(S3Client), bedrock = mockClient(BedrockRuntimeClient);
const cid = '00000000-0000-4000-8000-000000000001', aid = '00000000-0000-4000-8000-000000000003';
const objectKey = `attachments/${cid}/${aid}`;
const fileBytes = new Uint8Array([0xff, 0xd8, 0xff, 0x01]);
const secretDescription = 'Coffee leaves with orange rust spots.';
const log = { info: vi.fn(), warn: vi.fn(), error: vi.fn() };
const presign = vi.fn<AttachmentDeps['presign']>().mockResolvedValue({ url: 'https://upload.test', fields: { key: objectKey } });
const d: AttachmentDeps = { db: new DynamoDBClient({}), s3: new S3Client({}), bedrock: new BedrockRuntimeClient({}),
  conversations: 'chat', bucket: 'bucket', keyArn: 'key', modelId: 'us.anthropic.claude-haiku-5-5', log,
  now: () => 1000, clock: () => 0, newId: () => aid, presign };
type Kind = 'create' | 'read' | 'delete';
function event(kind: Kind, body: unknown = { content_type: 'image/jpeg' }, attachmentId = aid): APIGatewayProxyEvent {
  const resource = kind === 'create' ? '/conversations/{id}/attachments'
    : kind === 'read' ? '/conversations/{id}/attachments/{attachment_id}/read' : '/conversations/{id}/attachments/{attachment_id}';
  return { httpMethod: kind === 'delete' ? 'DELETE' : 'POST', resource,
    pathParameters: { id: cid, ...(kind === 'create' ? {} : { attachment_id: attachmentId }) },
    body: kind === 'create' ? (typeof body === 'string' ? body : JSON.stringify(body)) : null,
    requestContext: { authorizer: { userId: 'p', roles: 'producer', producerId: 'p' } },
  } as unknown as APIGatewayProxyEvent;
}
function conversation(owner = 'p', status = 'open', language = 'es') {
  db.on(GetItemCommand, { TableName: 'chat' }).resolves({ Item: marshall({ producer_id: owner, status, language }) });
}
function uploaded(contentType = 'image/jpeg', size = fileBytes.length) {
  s3.on(HeadObjectCommand).resolves({ ContentLength: size, ContentType: contentType });
  s3.on(GetObjectCommand).resolves({ Body: { transformToByteArray: async () => fileBytes } as never });
}
const missing = () => s3.on(HeadObjectCommand).rejects(Object.assign(new Error('NotFound'), { name: 'NotFound' }));
const allLogs = () => JSON.stringify([log.info.mock.calls, log.warn.mock.calls, log.error.mock.calls]);
beforeEach(() => {
  db.reset(); s3.reset(); bedrock.reset(); presign.mockClear();
  log.info.mockClear(); log.warn.mockClear(); log.error.mockClear();
  conversation(); uploaded(); s3.on(DeleteObjectCommand).resolves({});
  bedrock.on(ConverseCommand).resolves({ output: { message: { role: 'assistant',
    content: [{ text: 'Coffee leaves ' }, { text: 'with orange rust spots.' }] } } });
});
describe('attachment routes', () => {
  it.each<Kind>(['create', 'read', 'delete'])("hide another producer's conversation on %s", async kind => {
    conversation('other');
    await expect(attachmentsRoute(d, event(kind))).rejects.toThrow('Not found');
    expect(presign).not.toHaveBeenCalled(); expect(s3.calls()).toHaveLength(0); expect(bedrock.calls()).toHaveLength(0);
  });
  it.each<Kind>(['create', 'read', 'delete'])('return 409 on a closed conversation for %s', async kind => {
    conversation('p', 'closed');
    await expect(attachmentsRoute(d, event(kind))).rejects.toMatchObject({ name: 'Conflict' });
    expect(presign).not.toHaveBeenCalled(); expect(s3.calls()).toHaveLength(0); expect(bedrock.calls()).toHaveLength(0);
  });
  it.each<Kind>(['read', 'delete'])('treat a malformed attachment id as not found on %s', async kind => {
    await expect(attachmentsRoute(d, event(kind, undefined, '../voice'))).rejects.toThrow('Not found');
    expect(s3.calls()).toHaveLength(0);
  });
});
describe('creating an upload form', () => {
  it.each(['image/jpeg', 'image/png', 'image/webp', 'application/pdf'])('fixes prefix, %s, KMS and the 3.75 MB limit', async type => {
    const result = await attachmentsRoute(d, event('create', { content_type: type }));
    expect(result).toEqual({ statusCode: 201, body: { attachment_id: aid, upload: { url: 'https://upload.test', fields: { key: objectKey } }, expires_at: 1300 } });
    const options = presign.mock.calls[0]![1];
    expect(MAX_ATTACHMENT_BYTES).toBe(3_932_160);
    expect(options).toMatchObject({ Bucket: 'bucket', Key: objectKey, Expires: 300, Fields: { 'Content-Type': type,
      'x-amz-server-side-encryption': 'aws:kms', 'x-amz-server-side-encryption-aws-kms-key-id': 'key' } });
    expect(options.Conditions).toEqual(expect.arrayContaining([['content-length-range', 1, 3_932_160], ['eq', '$Content-Type', type],
      ['eq', '$x-amz-server-side-encryption', 'aws:kms'], ['eq', '$x-amz-server-side-encryption-aws-kms-key-id', 'key']]));
  });
  it.each([['another type', { content_type: 'image/gif' }], ['a missing type', {}],
    ['an unknown key', { content_type: 'image/png', key: 'attachments/x' }], ['invalid JSON', '{']])('rejects %s', async (_, body) => {
    await expect(attachmentsRoute(d, event('create', body))).rejects.toMatchObject({ name: 'BadRequest' });
    expect(presign).not.toHaveBeenCalled();
  });
});
describe('reading an attachment', () => {
  it.each([['image/jpeg', 'jpeg'], ['image/png', 'png'], ['image/webp', 'webp']])('sends %s as an image block and returns the joined text', async (type, format) => {
    uploaded(type);
    expect(await attachmentsRoute(d, event('read'))).toEqual({ statusCode: 200, body: { description: secretDescription } });
    const input = bedrock.commandCalls(ConverseCommand)[0]!.args[0].input;
    expect(input.modelId).toBe('us.anthropic.claude-haiku-5-5');
    expect(input.inferenceConfig).toEqual({ maxTokens: 200 });
    const content = input.messages![0]!.content!;
    expect(input.messages![0]!.role).toBe('user');
    expect(content[0]).toEqual({ image: { format, source: { bytes: fileBytes } } });
    expect(content[1]!.text).toContain('A Fair Trade producer attached this file');
    expect(content[1]!.text).toMatch(/Reply in Spanish\.$/);
    expect(s3.commandCalls(DeleteObjectCommand).map(c => c.args[0].input)).toEqual([{ Bucket: 'bucket', Key: objectKey }]);
  });
  it('sends a PDF as a document block', async () => {
    uploaded('application/pdf');
    await attachmentsRoute(d, event('read'));
    expect(bedrock.commandCalls(ConverseCommand)[0]!.args[0].input.messages![0]!.content![0])
      .toEqual({ document: { format: 'pdf', name: 'attachment', source: { bytes: fileBytes } } });
  });
  it.each([['en', 'English'], ['fr', 'French'], ['xx', 'English']])('asks for a reply in the language of %s', async (language, name) => {
    conversation('p', 'open', language);
    await attachmentsRoute(d, event('read'));
    expect(bedrock.commandCalls(ConverseCommand)[0]!.args[0].input.messages![0]!.content![1]!.text).toMatch(new RegExp(`Reply in ${name}\\.$`));
  });
  it('uses the full spec prompt', async () => {
    await attachmentsRoute(d, event('read'));
    expect(bedrock.commandCalls(ConverseCommand)[0]!.args[0].input.messages![0]!.content![1]!.text).toBe(
      'A Fair Trade producer attached this file to describe a challenge on their farm or in their organization. In one or two short sentences, state factually what it shows that is relevant to farming, water, crops, land, labour or prices. Do not name or describe any person, and do not include names, phone numbers, IDs or addresses. If nothing relevant is visible, say so. Reply in Spanish.');
  });
  it('deletes the object even when Bedrock fails', async () => {
    bedrock.on(ConverseCommand).rejects(Object.assign(new Error('Throttled'), { name: 'ThrottlingException' }));
    await expect(attachmentsRoute(d, event('read'))).rejects.toThrow('Throttled');
    expect(s3.commandCalls(DeleteObjectCommand).map(c => c.args[0].input.Key)).toEqual([objectKey]);
  });
  it('deletes the object even when the download fails', async () => {
    s3.on(GetObjectCommand).rejects(new Error('Reset'));
    await expect(attachmentsRoute(d, event('read'))).rejects.toThrow('Reset');
    expect(s3.commandCalls(DeleteObjectCommand)).toHaveLength(1); expect(bedrock.calls()).toHaveLength(0);
  });
  it('returns 404 on a second read because the file is gone', async () => {
    await attachmentsRoute(d, event('read'));
    missing();
    await expect(attachmentsRoute(d, event('read'))).rejects.toThrow('Not found');
    expect(bedrock.commandCalls(ConverseCommand)).toHaveLength(1);
  });
  it.each([['over the limit', 'image/png', MAX_ATTACHMENT_BYTES + 1], ['empty', 'image/png', 0],
    ['a disallowed type', 'image/gif', 10], ['without a type', '', 10]])('rejects and deletes an object %s', async (_, type, size) => {
    uploaded(type, size);
    await expect(attachmentsRoute(d, event('read'))).rejects.toMatchObject({ name: 'BadRequest' });
    expect(s3.commandCalls(DeleteObjectCommand).map(c => c.args[0].input.Key)).toEqual([objectKey]);
    expect(s3.commandCalls(GetObjectCommand)).toHaveLength(0); expect(bedrock.calls()).toHaveLength(0);
  });
  it('accepts exactly 3.75 MB', async () => {
    uploaded('image/png', MAX_ATTACHMENT_BYTES);
    expect((await attachmentsRoute(d, event('read'))).statusCode).toBe(200);
  });
});
describe('cancelling an attachment', () => {
  it('deletes the object and returns 200', async () => {
    expect(await attachmentsRoute(d, event('delete'))).toEqual({ statusCode: 200, body: { status: 'deleted' } });
    expect(s3.commandCalls(DeleteObjectCommand).map(c => c.args[0].input)).toEqual([{ Bucket: 'bucket', Key: objectKey }]);
  });
  it('returns 200 when the object is already gone', async () => {
    missing();
    expect((await attachmentsRoute(d, event('delete'))).statusCode).toBe(200);
  });
});
describe('logging', () => {
  it('records ids, type, size and duration only, never the description or file', async () => {
    await attachmentsRoute(d, event('create'));
    await attachmentsRoute(d, event('read'));
    await attachmentsRoute(d, event('delete'));
    const read = log.info.mock.calls.find(([message]) => message === 'Attachment read')!;
    expect(Object.keys(read[1]).sort()).toEqual(['attachment_id', 'bytes', 'content_type', 'conversation_id', 'duration_ms']);
    for (const [, fields] of log.info.mock.calls) {
      for (const k of Object.keys(fields)) expect(['attachment_id', 'bytes', 'content_type', 'conversation_id', 'duration_ms']).toContain(k);
    }
    expect(allLogs()).not.toMatch(/rust|Coffee|Fair Trade producer/);
  });
  it('logs nothing about the content when Bedrock fails', async () => {
    bedrock.on(ConverseCommand).rejects(new Error('Model said: Coffee'));
    await expect(attachmentsRoute(d, event('read'))).rejects.toThrow();
    expect(allLogs()).not.toContain('Coffee');
  });
});
