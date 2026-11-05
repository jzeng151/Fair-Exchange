import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mockClient } from 'aws-sdk-client-mock';
import { DynamoDBClient, GetItemCommand, PutItemCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { S3Client, GetObjectCommand, DeleteObjectCommand, HeadObjectCommand } from '@aws-sdk/client-s3';
import { TranscribeClient, GetTranscriptionJobCommand, StartTranscriptionJobCommand } from '@aws-sdk/client-transcribe';
import { TranslateClient, TranslateTextCommand } from '@aws-sdk/client-translate';
import { marshall } from '@aws-sdk/util-dynamodb';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { completeVoice, MAX_BYTES, voiceRoute, type VoiceDeps, type VoiceItem } from './service.js';
const db = mockClient(DynamoDBClient), s3 = mockClient(S3Client), transcribe = mockClient(TranscribeClient), translate = mockClient(TranslateClient);
const cid = '00000000-0000-4000-8000-000000000001', vid = '00000000-0000-4000-8000-000000000002';
const base: VoiceItem = { voice_id: vid, conversation_id: cid, status: 'pending', expires_at: 4600,
  content_type: 'audio/webm', audio_key: `audio/${cid}/${vid}.webm`, output_key: `transcripts/${vid}.json` };
const presign = vi.fn<VoiceDeps['presign']>().mockResolvedValue({ url: 'https://upload.test', fields: { key: base.audio_key } });
const d: VoiceDeps = { db: new DynamoDBClient({}), s3: new S3Client({}), transcribe: new TranscribeClient({}),
  translate: new TranslateClient({}), table: 'voice', conversations: 'chat', bucket: 'bucket', keyArn: 'key', dataRole: 'role',
  jobPrefix: 'Test-voice-', now: () => 1000, newId: () => vid, presign };
function event(method = 'GET', suffix = '', create = false): APIGatewayProxyEvent {
  return { httpMethod: method, resource: `/conversations/{id}/voice/{voice_id}${suffix}`,
    pathParameters: { id: cid, ...(create ? {} : { voice_id: vid }) },
    body: JSON.stringify({ content_type: 'audio/webm' }),
    requestContext: { authorizer: { userId: 'p', roles: 'producer', producerId: 'p' } },
  } as unknown as APIGatewayProxyEvent;
}
function conversation(owner = 'p', status = 'open') {
  db.on(GetItemCommand, { TableName: 'chat' }).resolves({ Item: marshall({ producer_id: owner, status, language: 'es' }) });
}
function item(value: VoiceItem = base) { db.on(GetItemCommand, { TableName: 'voice' }).resolves({ Item: marshall(value) }); }
function completed(status: 'COMPLETED' | 'FAILED' = 'COMPLETED') {
  transcribe.on(GetTranscriptionJobCommand).resolves({ TranscriptionJob: { TranscriptionJobStatus: status, LanguageCode: 'es-US',
    Media: { MediaFileUri: `s3://bucket/${base.audio_key}` } } });
  // Only the SDK stream helper used by the module is needed here.
  s3.on(GetObjectCommand).resolves({ Body: { transformToString: async () => JSON.stringify({ results: { transcripts: [{ transcript: 'Lluvia irregular.' }] } }) } as never });
  translate.on(TranslateTextCommand).resolves({ TranslatedText: 'Irregular rain.' });
}
beforeEach(() => {
  db.reset(); s3.reset(); transcribe.reset(); translate.reset(); presign.mockClear();
  conversation(); item(); db.on(PutItemCommand).resolves({}); db.on(UpdateItemCommand).resolves({});
  s3.on(DeleteObjectCommand).resolves({}); s3.on(HeadObjectCommand).resolves({ ContentLength: 1000, ContentType: 'audio/webm' });
  transcribe.on(StartTranscriptionJobCommand).resolves({});
});
describe('voice routes', () => {
  it.each([['POST', '', true], ['POST', '/transcribe', false], ['GET', '', false], ['DELETE', '', false]])('hides other producers on %s %s', async (method, suffix, create) => {
    conversation('other'); await expect(voiceRoute(d, event(String(method), String(suffix), Boolean(create)))).rejects.toThrow('Not found');
    expect(db.commandCalls(PutItemCommand)).toHaveLength(0); expect(transcribe.calls()).toHaveLength(0);
  });
  it.each(['POST', 'GET', 'DELETE'])('rejects closed conversations on %s', async method => {
    conversation('p', 'closed'); await expect(voiceRoute(d, event(method))).rejects.toThrow('closed');
  });
  it('creates a short-lived, size-limited encrypted form with a server-owned key', async () => {
    expect((await voiceRoute(d, event('POST', '', true))).statusCode).toBe(201);
    const options = presign.mock.calls[0]![1];
    expect(options).toMatchObject({ Expires: 300, Key: base.audio_key, Fields: { 'Content-Type': 'audio/webm', 'x-amz-server-side-encryption': 'aws:kms' } });
    expect(options.Conditions).toContainEqual(['content-length-range', 1, MAX_BYTES]);
    expect(options.Conditions).toContainEqual(['eq', '$Content-Type', 'audio/webm']);
  });
  it('starts only a verified upload with the scoped role, known language and encrypted output', async () => {
    expect((await voiceRoute(d, event('POST', '/transcribe'))).statusCode).toBe(202);
    expect(transcribe.commandCalls(StartTranscriptionJobCommand)[0]!.args[0].input).toMatchObject({
      TranscriptionJobName: d.jobPrefix + vid, LanguageCode: 'es-US', OutputEncryptionKMSKeyId: 'key',
      JobExecutionSettings: { DataAccessRoleArn: 'role' }, OutputKey: base.output_key });
  });
  it('rejects an oversized object before starting Transcribe', async () => {
    s3.on(HeadObjectCommand).resolves({ ContentLength: MAX_BYTES + 1, ContentType: 'audio/webm' });
    await expect(voiceRoute(d, event('POST', '/transcribe'))).rejects.toThrow('Invalid recording');
    expect(transcribe.calls()).toHaveLength(0);
  });
  it('does not start a cancelled note', async () => {
    item({ ...base, status: 'cancelled' });
    await expect(voiceRoute(d, event('POST', '/transcribe'))).rejects.toThrow('no longer pending');
    expect(transcribe.calls()).toHaveLength(0);
  });
  it('removes both transcript versions and objects on cancellation', async () => {
    expect((await voiceRoute(d, event('DELETE'))).body).toEqual({ status: 'cancelled' });
    expect(db.commandCalls(UpdateItemCommand)[0]!.args[0].input.UpdateExpression).toContain('REMOVE transcript, transcript_english');
    expect(s3.commandCalls(DeleteObjectCommand).map(c => c.args[0].input.Key).sort()).toEqual([base.audio_key, base.output_key].sort());
  });
  it('delivers both transcripts once using a conditional consume', async () => {
    const done = { ...base, status: 'done' as const, transcript: 'Lluvia', transcript_english: 'Rain' }; item(done);
    db.on(UpdateItemCommand).resolves({ Attributes: marshall(done) });
    expect((await voiceRoute(d, event())).body).toEqual({ status: 'done', transcript: 'Lluvia', transcript_english: 'Rain' });
    expect(db.commandCalls(UpdateItemCommand)[0]!.args[0].input.ConditionExpression).toBe('#s = :done AND expires_at > :now');
    item({ ...base, status: 'delivered' }); expect((await voiceRoute(d, event())).body).toEqual({ status: 'delivered' });
  });
  it('never returns an expired transcript while waiting for DynamoDB TTL', async () => {
    item({ ...base, status: 'done', transcript: 'Private', expires_at: 999 });
    await expect(voiceRoute(d, event())).rejects.toThrow('Not found');
  });
});
describe('completion without a browser', () => {
  it('stores a translated transcript and deletes both objects', async () => {
    completed(); await completeVoice(d, d.jobPrefix + vid);
    expect(db.commandCalls(UpdateItemCommand)[0]!.args[0].input.ExpressionAttributeValues).toMatchObject({
      ':next': { S: 'done' }, ':text': { S: 'Lluvia irregular.' }, ':english': { S: 'Irregular rain.' } });
    expect(s3.commandCalls(DeleteObjectCommand)).toHaveLength(2);
  });
  it('delivers the original when translation fails', async () => {
    completed(); translate.on(TranslateTextCommand).rejects('Unavailable'); await completeVoice(d, d.jobPrefix + vid);
    expect(db.commandCalls(UpdateItemCommand)[0]!.args[0].input.ExpressionAttributeValues).not.toHaveProperty(':english');
    expect(s3.commandCalls(DeleteObjectCommand)).toHaveLength(2);
  });
  it('cannot restore a transcript when cancellation wins the update race', async () => {
    completed(); db.on(UpdateItemCommand).callsFake(input => {
      expect(input.ConditionExpression).toBe('#s = :pending AND expires_at > :now');
      throw Object.assign(new Error('Race lost'), { name: 'ConditionalCheckFailedException' });
    });
    await completeVoice(d, d.jobPrefix + vid); expect(s3.commandCalls(DeleteObjectCommand)).toHaveLength(2);
  });
  it.each(['cancelled', 'delivered'] as const)('does not fetch or resurrect a %s transcript on duplicate completion', async status => {
    completed(); item({ ...base, status }); await completeVoice(d, d.jobPrefix + vid);
    expect(s3.commandCalls(GetObjectCommand)).toHaveLength(0); expect(db.commandCalls(UpdateItemCommand)).toHaveLength(0);
    expect(s3.commandCalls(DeleteObjectCommand)).toHaveLength(2);
  });
  it('cleans up failed jobs and marks the note failed', async () => {
    completed('FAILED'); await completeVoice(d, d.jobPrefix + vid);
    expect(db.commandCalls(UpdateItemCommand)[0]!.args[0].input.ExpressionAttributeValues?.[':next']).toEqual({ S: 'failed' });
    expect(s3.commandCalls(DeleteObjectCommand)).toHaveLength(2);
  });
  it('keeps the only transcript copy when a database error requires a retry', async () => {
    completed(); db.on(UpdateItemCommand).rejects('DynamoDB unavailable');
    await expect(completeVoice(d, d.jobPrefix + vid)).rejects.toThrow();
    expect(s3.commandCalls(DeleteObjectCommand)).toHaveLength(0);
  });
  it('ignores unrelated job names', async () => { await completeVoice(d, 'Other-voice-' + vid); expect(transcribe.calls()).toHaveLength(0); });
});
