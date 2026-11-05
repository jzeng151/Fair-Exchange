import { randomUUID } from 'node:crypto';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { S3Client, DeleteObjectCommand, GetObjectCommand, HeadObjectCommand } from '@aws-sdk/client-s3';
import { createPresignedPost } from '@aws-sdk/s3-presigned-post';
import { BedrockRuntimeClient, ConverseCommand, type ContentBlock } from '@aws-sdk/client-bedrock-runtime';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { loadOwnedConversation } from '../core/ownedConversation.js';
import { BadRequest, isConversationId, parseAttachmentBody } from '../core/validate.js';
import { Conflict, NotFound } from '../core/turn.js';
import { json } from '../core/routes.js';
import type { Log } from '../core/types.js';

/** 3.75 MB, Bedrock's image limit (#169). */
export const MAX_ATTACHMENT_BYTES = 3_932_160;
const FORM_SECONDS = 300;
const TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'] as const;
type AttachmentType = (typeof TYPES)[number];
const IMAGE_FORMATS = { 'image/jpeg': 'jpeg', 'image/png': 'png', 'image/webp': 'webp' } as const;
const LANGUAGES: Record<string, string> = { en: 'English', es: 'Spanish', fr: 'French' };
export const prompt = (language: string) => 'A Fair Trade producer attached this file to describe a challenge on their farm or in their organization. '
  + 'In one or two short sentences, state factually what it shows that is relevant to farming, water, crops, land, labour or prices. '
  + 'Do not name or describe any person, and do not include names, phone numbers, IDs or addresses. '
  + `If nothing relevant is visible, say so. Reply in ${language}.`;

export interface AttachmentDeps {
  db: DynamoDBClient; s3: S3Client; bedrock: BedrockRuntimeClient;
  conversations: string; bucket: string; keyArn: string; modelId: string; log: Log;
  now: () => number; clock: () => number; newId: () => string; presign: typeof createPresignedPost;
}
export function attachmentDeps(log: Log): AttachmentDeps {
  const env = (key: string) => { const value = process.env[key]; if (!value) throw new Error(`Missing ${key}`); return value; };
  return { db: new DynamoDBClient({}), s3: new S3Client({}), bedrock: new BedrockRuntimeClient({}),
    conversations: env('CONVERSATIONS_TABLE'), bucket: env('ATTACHMENT_BUCKET'), keyArn: env('ATTACHMENT_KEY_ARN'),
    modelId: env('ATTACHMENT_MODEL_ID'), log, now: () => Math.floor(Date.now() / 1000), clock: () => Date.now(),
    newId: randomUUID, presign: createPresignedPost };
}
const isType = (value: string | undefined): value is AttachmentType => TYPES.includes(value as AttachmentType);
const missing = (e: unknown) => e instanceof Error && ['NotFound', 'NoSuchKey'].includes(e.name);

/**
 * The file is the only state: its key carries the conversation ID, so the ownership check covers it,
 * and it is deleted after one read (or on cancel). The description is returned, never stored.
 */
export async function attachmentsRoute(d: AttachmentDeps, event: APIGatewayProxyEvent) {
  const started = d.clock();
  const conversation = await loadOwnedConversation(d.db, d.conversations, event);
  if (conversation.status !== 'open') throw new Conflict('Conversation is closed');
  const attachmentId = event.pathParameters?.attachment_id;
  if (attachmentId === undefined && event.httpMethod === 'POST') {
    const { content_type: contentType } = parseAttachmentBody(event.body, TYPES);
    const id = d.newId();
    const upload = await d.presign(d.s3, { Bucket: d.bucket, Key: `attachments/${conversation.id}/${id}`, Expires: FORM_SECONDS,
      Fields: { 'Content-Type': contentType, 'x-amz-server-side-encryption': 'aws:kms',
        'x-amz-server-side-encryption-aws-kms-key-id': d.keyArn },
      Conditions: [['content-length-range', 1, MAX_ATTACHMENT_BYTES], ['eq', '$Content-Type', contentType],
        ['eq', '$x-amz-server-side-encryption', 'aws:kms'], ['eq', '$x-amz-server-side-encryption-aws-kms-key-id', d.keyArn]] });
    d.log.info('Attachment form created', { conversation_id: conversation.id, attachment_id: id, content_type: contentType });
    return json(201, { attachment_id: id, upload, expires_at: d.now() + FORM_SECONDS });
  }
  if (!isConversationId(attachmentId)) throw new NotFound();
  const object = { Bucket: d.bucket, Key: `attachments/${conversation.id}/${attachmentId}` };
  const ids = { conversation_id: conversation.id, attachment_id: attachmentId };
  if (event.httpMethod === 'DELETE') {
    await d.s3.send(new DeleteObjectCommand(object)); // S3 deletes are idempotent: 200 whether or not it was there.
    d.log.info('Attachment cancelled', ids);
    return json(200, { status: 'deleted' });
  }
  if (event.httpMethod !== 'POST' || !event.resource.endsWith('/read')) throw new NotFound();
  let head;
  try { head = await d.s3.send(new HeadObjectCommand(object)); }
  catch (e) { if (missing(e)) throw new NotFound(); throw e; }
  try {
    const size = head.ContentLength ?? 0;
    const contentType = head.ContentType;
    if (!isType(contentType) || size < 1 || size > MAX_ATTACHMENT_BYTES) throw new BadRequest('Invalid attachment');
    const body = await d.s3.send(new GetObjectCommand(object));
    if (!body.Body) throw new Error('Empty attachment body');
    const bytes = await body.Body.transformToByteArray();
    const file: ContentBlock = contentType === 'application/pdf'
      ? { document: { format: 'pdf', name: 'attachment', source: { bytes } } }
      : { image: { format: IMAGE_FORMATS[contentType], source: { bytes } } };
    const result = await d.bedrock.send(new ConverseCommand({ modelId: d.modelId,
      messages: [{ role: 'user', content: [file, { text: prompt(LANGUAGES[conversation.language ?? ''] ?? 'English') }] }],
      inferenceConfig: { maxTokens: 200 } }));
    const description = (result.output?.message?.content ?? []).map(block => block.text ?? '').join('').trim();
    if (!description) throw new Error('Empty description');
    d.log.info('Attachment read', { ...ids, content_type: contentType, bytes: size, duration_ms: d.clock() - started });
    return json(200, { description });
  } finally {
    // Whether or not the read succeeds, the file must not outlive this request.
    await d.s3.send(new DeleteObjectCommand(object));
  }
}
