import { randomUUID } from 'node:crypto';
import { DynamoDBClient, GetItemCommand, PutItemCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { marshall, unmarshall } from '@aws-sdk/util-dynamodb';
import { S3Client, HeadObjectCommand, DeleteObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
import { createPresignedPost } from '@aws-sdk/s3-presigned-post';
import { TranscribeClient, StartTranscriptionJobCommand, GetTranscriptionJobCommand } from '@aws-sdk/client-transcribe';
import { TranslateClient, TranslateTextCommand } from '@aws-sdk/client-translate';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { resolveIdentity, requireRole } from '../core/identity.js';
import { BadRequest, isConversationId } from '../core/validate.js';
import { Conflict, NotFound } from '../core/turn.js';
import { json } from '../core/routes.js';

export const MAX_BYTES = 5 * 1024 * 1024;
export interface VoiceItem {
  voice_id: string; conversation_id: string; status: 'pending' | 'done' | 'delivered' | 'failed' | 'cancelled';
  expires_at: number; content_type: 'audio/webm' | 'audio/mp4'; audio_key: string; output_key: string;
  started?: boolean; transcript?: string; transcript_english?: string;
}
export interface VoiceDeps {
  db: DynamoDBClient; s3: S3Client; transcribe: TranscribeClient; translate: TranslateClient;
  table: string; conversations: string; bucket: string; keyArn: string; dataRole: string; jobPrefix: string;
  now: () => number; newId: () => string; presign: typeof createPresignedPost;
}
export function voiceDeps(): VoiceDeps {
  const env = (key: string) => { const value = process.env[key]; if (!value) throw new Error(`Missing ${key}`); return value; };
  return { db: new DynamoDBClient({}), s3: new S3Client({}), transcribe: new TranscribeClient({}),
    translate: new TranslateClient({}), table: env('VOICE_TABLE'), conversations: env('CONVERSATIONS_TABLE'),
    bucket: env('VOICE_BUCKET'), keyArn: env('VOICE_KEY_ARN'), dataRole: env('VOICE_DATA_ROLE'),
    jobPrefix: env('VOICE_JOB_PREFIX'), now: () => Math.floor(Date.now() / 1000), newId: randomUUID, presign: createPresignedPost };
}
const conditional = (e: unknown) => e instanceof Error && e.name === 'ConditionalCheckFailedException';
const key = (voiceId: string) => ({ voice_id: { S: voiceId } });
async function load(d: VoiceDeps, voiceId: string): Promise<VoiceItem | undefined> {
  const r = await d.db.send(new GetItemCommand({ TableName: d.table, Key: key(voiceId), ConsistentRead: true }));
  return r.Item ? unmarshall(r.Item) as VoiceItem : undefined;
}
async function cleanup(d: VoiceDeps, keys: string[]) {
  await Promise.all(keys.map(Key => d.s3.send(new DeleteObjectCommand({ Bucket: d.bucket, Key }))));
}

/** Every operation resolves the producer from the authorizer and rechecks conversation ownership. */
export async function voiceRoute(d: VoiceDeps, event: APIGatewayProxyEvent) {
  const identity = requireRole(await resolveIdentity(event), 'producer');
  const id = event.pathParameters?.id;
  if (!identity.producerId || !isConversationId(id)) throw new NotFound();
  const result = await d.db.send(new GetItemCommand({ TableName: d.conversations,
    Key: { conversation_id: { S: id } }, ConsistentRead: true }));
  const conversation = result.Item && unmarshall(result.Item);
  if (!conversation || conversation.producer_id !== identity.producerId) throw new NotFound();
  if (conversation.status !== 'open') throw new Conflict('Conversation is closed');
  const method = event.httpMethod;
  const voiceId = event.pathParameters?.voice_id;
  if (!voiceId && method === 'POST') {
    let body: Record<string, unknown>;
    try { body = JSON.parse(event.body ?? '{}'); } catch { throw new BadRequest('Invalid JSON'); }
    if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).some(k => k !== 'content_type')
      || !['audio/webm', 'audio/mp4'].includes(String(body.content_type))) throw new BadRequest('Choose audio/webm or audio/mp4');
    const contentType = body.content_type as VoiceItem['content_type'];
    const vid = d.newId();
    const item: VoiceItem = { voice_id: vid, conversation_id: id, status: 'pending', expires_at: d.now() + 3600,
      content_type: contentType, audio_key: `audio/${id}/${vid}.${contentType === 'audio/mp4' ? 'mp4' : 'webm'}`,
      output_key: `transcripts/${vid}.json` };
    const upload = await d.presign(d.s3, { Bucket: d.bucket, Key: item.audio_key, Expires: 300,
      Fields: { 'Content-Type': contentType, 'x-amz-server-side-encryption': 'aws:kms',
        'x-amz-server-side-encryption-aws-kms-key-id': d.keyArn },
      Conditions: [['content-length-range', 1, MAX_BYTES], ['eq', '$Content-Type', contentType],
        ['eq', '$x-amz-server-side-encryption', 'aws:kms'], ['eq', '$x-amz-server-side-encryption-aws-kms-key-id', d.keyArn]] });
    await d.db.send(new PutItemCommand({ TableName: d.table, Item: marshall(item), ConditionExpression: 'attribute_not_exists(voice_id)' }));
    return json(201, { voice_id: vid, upload, expires_at: item.expires_at });
  }
  if (!isConversationId(voiceId)) throw new NotFound();
  const item = await load(d, voiceId);
  if (!item || item.conversation_id !== id || item.expires_at <= d.now()) throw new NotFound();
  if (method === 'DELETE') {
    await d.db.send(new UpdateItemCommand({ TableName: d.table, Key: key(voiceId),
      UpdateExpression: 'SET #s = :cancelled REMOVE transcript, transcript_english',
      ConditionExpression: 'attribute_exists(voice_id)', ExpressionAttributeNames: { '#s': 'status' },
      ExpressionAttributeValues: { ':cancelled': { S: 'cancelled' } } }));
    await cleanup(d, [item.audio_key, item.output_key]);
    return json(200, { status: 'cancelled' });
  }
  if (method === 'GET') {
    if (item.status !== 'done') return json(200, { status: item.status });
    try {
      // Return ALL_OLD only to the winner: concurrent polls cannot deliver the transcript twice.
      const delivered = await d.db.send(new UpdateItemCommand({ TableName: d.table, Key: key(voiceId),
        UpdateExpression: 'SET #s = :delivered REMOVE transcript, transcript_english',
        ConditionExpression: '#s = :done AND expires_at > :now', ReturnValues: 'ALL_OLD',
        ExpressionAttributeNames: { '#s': 'status' }, ExpressionAttributeValues: {
          ':done': { S: 'done' }, ':delivered': { S: 'delivered' }, ':now': { N: String(d.now()) } } }));
      const old = delivered.Attributes && unmarshall(delivered.Attributes);
      if (!old?.transcript) throw new Error('Missing transcript');
      return json(200, { status: 'done', transcript: old.transcript,
        ...(old.transcript_english ? { transcript_english: old.transcript_english } : {}) });
    } catch (e) {
      if (!conditional(e)) throw e;
      const fresh = await load(d, voiceId);
      if (!fresh || fresh.expires_at <= d.now()) throw new NotFound();
      return json(200, { status: fresh.status });
    }
  }
  if (method !== 'POST' || !event.resource.endsWith('/transcribe')) throw new NotFound();
  if (item.status !== 'pending') throw new Conflict('Voice note is no longer pending');
  if (!item.started) {
    let object;
    try { object = await d.s3.send(new HeadObjectCommand({ Bucket: d.bucket, Key: item.audio_key })); }
    catch (e) { if (e instanceof Error && ['NotFound', 'NoSuchKey'].includes(e.name)) throw new BadRequest('Upload the recording first'); throw e; }
    if (!object.ContentLength || object.ContentLength > MAX_BYTES || object.ContentType !== item.content_type) throw new BadRequest('Invalid recording');
    try {
      await d.db.send(new UpdateItemCommand({ TableName: d.table, Key: key(voiceId),
        UpdateExpression: 'SET started = :yes', ConditionExpression: '#s = :pending AND expires_at > :now AND attribute_not_exists(started)',
        ExpressionAttributeNames: { '#s': 'status' }, ExpressionAttributeValues: {
          ':yes': { BOOL: true }, ':pending': { S: 'pending' }, ':now': { N: String(d.now()) } } }));
    } catch (e) { if (conditional(e)) throw new Conflict('Voice note changed; retry'); throw e; }
  }
  // Fixed job name makes retries after an ambiguous network response idempotent.
  const language = ({ en: 'en-US', es: 'es-US', fr: 'fr-FR' } as const)[conversation.language as 'en' | 'es' | 'fr'];
  try {
    await d.transcribe.send(new StartTranscriptionJobCommand({ TranscriptionJobName: d.jobPrefix + voiceId,
      Media: { MediaFileUri: `s3://${d.bucket}/${item.audio_key}` }, MediaFormat: item.content_type === 'audio/mp4' ? 'mp4' : 'webm',
      ...(language ? { LanguageCode: language } : { IdentifyLanguage: true, LanguageOptions: ['en-US', 'es-US', 'fr-FR'] }),
      OutputBucketName: d.bucket, OutputKey: item.output_key, OutputEncryptionKMSKeyId: d.keyArn,
      JobExecutionSettings: { AllowDeferredExecution: true, DataAccessRoleArn: d.dataRole } }));
  } catch (e) { if (!(e instanceof Error && e.name === 'ConflictException')) throw e; }
  return json(202, { status: 'pending' });
}

/** EventBridge owns completion and cleanup; browser polling is never required. */
export async function completeVoice(d: VoiceDeps, jobName: string) {
  if (!jobName.startsWith(d.jobPrefix)) return;
  const vid = jobName.slice(d.jobPrefix.length);
  if (!isConversationId(vid)) return;
  const job = (await d.transcribe.send(new GetTranscriptionJobCommand({ TranscriptionJobName: jobName }))).TranscriptionJob;
  if (!job || !['COMPLETED', 'FAILED'].includes(job.TranscriptionJobStatus ?? '')) return;
  const item = await load(d, vid);
  const outputKey = `transcripts/${vid}.json`;
  // The job's own S3 URI is used only for cleanup if TTL has already removed the item.
  const media = job.Media?.MediaFileUri ?? '';
  const prefix = `s3://${d.bucket}/audio/`;
  const audioKey = item?.audio_key ?? (media.startsWith(prefix) && new RegExp(`/[a-f0-9-]{36}/${vid}\\.(webm|mp4)$`).test(media)
    ? media.slice(`s3://${d.bucket}/`.length) : undefined);
  if (item?.status === 'pending' && item.expires_at > d.now()) {
    let transcript = ''; let english: string | undefined;
    if (job.TranscriptionJobStatus === 'COMPLETED') {
      const object = await d.s3.send(new GetObjectCommand({ Bucket: d.bucket, Key: outputKey }));
      const data = JSON.parse(await object.Body!.transformToString());
      transcript = data.results?.transcripts?.[0]?.transcript?.trim() ?? '';
      const language = job.LanguageCode?.split('-')[0] ?? data.results?.language_code?.split('-')[0];
      if (transcript && language && language !== 'en') {
        try { english = (await d.translate.send(new TranslateTextCommand({ Text: transcript, SourceLanguageCode: language, TargetLanguageCode: 'en' }))).TranslatedText; }
        catch { /* Translation is optional. Do not log transcript or service errors. */ }
      }
    }
    try {
      await d.db.send(new UpdateItemCommand({ TableName: d.table, Key: key(vid),
        UpdateExpression: 'SET #s = :next' + (transcript ? ', transcript = :text' : '') + (english ? ', transcript_english = :english' : ''),
        ConditionExpression: '#s = :pending AND expires_at > :now', ExpressionAttributeNames: { '#s': 'status' },
        ExpressionAttributeValues: { ':next': { S: transcript ? 'done' : 'failed' }, ':pending': { S: 'pending' },
          ':now': { N: String(d.now()) }, ...(transcript ? { ':text': { S: transcript } } : {}), ...(english ? { ':english': { S: english } } : {}) } }));
    } catch (e) { if (!conditional(e)) throw e; }
  }
  // Failed DB writes retry without deleting the only transcript copy. Duplicate completion only cleans up.
  await cleanup(d, [outputKey, ...(audioKey ? [audioKey] : [])]);
}
