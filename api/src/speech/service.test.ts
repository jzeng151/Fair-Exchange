import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mockClient } from 'aws-sdk-client-mock';
import { DynamoDBClient, GetItemCommand } from '@aws-sdk/client-dynamodb';
import { PollyClient, SynthesizeSpeechCommand } from '@aws-sdk/client-polly';
import { marshall } from '@aws-sdk/util-dynamodb';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { MAX_SPEECH_CHARS, speechRoute, type SpeechDeps } from './service.js';
const db = mockClient(DynamoDBClient), polly = mockClient(PollyClient);
const cid = '00000000-0000-4000-8000-000000000001';
const secret = 'Mi parcela se inunda cada año';
const log = { info: vi.fn(), warn: vi.fn(), error: vi.fn() };
let clock = 0;
const d: SpeechDeps = { db: new DynamoDBClient({}), polly: new PollyClient({}), conversations: 'chat', log, clock: () => (clock += 25) };
function event(body: unknown = { text: secret }, owner = 'p'): APIGatewayProxyEvent {
  return { httpMethod: 'POST', resource: '/conversations/{id}/speech', pathParameters: { id: cid },
    body: typeof body === 'string' ? body : JSON.stringify(body),
    requestContext: { authorizer: { userId: owner, roles: 'producer', producerId: owner } },
  } as unknown as APIGatewayProxyEvent;
}
function conversation(owner = 'p', status = 'open', language: unknown = 'es') {
  db.on(GetItemCommand, { TableName: 'chat' }).resolves({ Item: marshall({ producer_id: owner, status, ...(language ? { language } : {}) }) });
}
const audio = new Uint8Array([0x49, 0x44, 0x33, 1, 2, 3]);
beforeEach(() => {
  db.reset(); polly.reset(); log.info.mockClear(); log.warn.mockClear(); log.error.mockClear();
  conversation();
  polly.on(SynthesizeSpeechCommand).resolves({ AudioStream: { transformToByteArray: async () => audio } as never, ContentType: 'audio/mpeg' });
});
describe('speech route', () => {
  it("hides another producer's conversation", async () => {
    conversation('other'); await expect(speechRoute(d, event())).rejects.toThrow('Not found');
    expect(polly.calls()).toHaveLength(0);
  });
  it('rejects a malformed conversation id as not found', async () => {
    const e = event(); e.pathParameters = { id: 'nope' };
    await expect(speechRoute(d, e)).rejects.toThrow('Not found');
  });
  it.each(['open', 'closed'])('reads text aloud on an %s conversation and returns base64 MP3', async status => {
    conversation('p', status);
    const result = await speechRoute(d, event());
    expect(result).toEqual({ statusCode: 200, body: { content_type: 'audio/mpeg', audio: Buffer.from(audio).toString('base64') } });
  });
  it.each([['en', 'Joanna', 'en-US'], ['es', 'Lupe', 'es-US'], ['fr', 'Lea', 'fr-FR'], ['de', 'Joanna', 'en-US'], [null, 'Joanna', 'en-US']])(
    'stored language %s picks %s neural', async (language, voice, code) => {
      conversation('p', 'open', language);
      await speechRoute(d, event());
      expect(polly.commandCalls(SynthesizeSpeechCommand)[0]!.args[0].input).toEqual({
        Text: secret, VoiceId: voice, LanguageCode: code, Engine: 'neural', OutputFormat: 'mp3', TextType: 'text' });
    });
  it('never takes the language from the request', async () => {
    conversation('p', 'open', 'fr');
    await expect(speechRoute(d, event({ text: 'hi', language: 'es' }))).rejects.toThrow('Unknown field: language');
    await speechRoute(d, event({ text: 'hi' }));
    expect(polly.commandCalls(SynthesizeSpeechCommand)[0]!.args[0].input.VoiceId).toBe('Lea');
  });
  it.each([
    ['empty text', { text: '' }], ['missing text', {}], ['non-string text', { text: 3 }],
    ['an unknown key', { text: 'hi', voice: 'Joanna' }], ['a conversation id', { text: 'hi', conversation_id: cid }],
    ['too many UTF-16 units', { text: 'a'.repeat(MAX_SPEECH_CHARS + 1) }],
    // 751 emoji are 751 code points but 1,502 UTF-16 units.
    ['emoji over the UTF-16 limit', { text: '\u{1F33D}'.repeat(751) }],
    ['an array', ['hi']], ['invalid JSON', '{'],
  ])('rejects %s', async (_, body) => {
    await expect(speechRoute(d, event(body))).rejects.toMatchObject({ name: 'BadRequest' });
    expect(polly.calls()).toHaveLength(0);
  });
  it('accepts exactly 1,500 UTF-16 units of emoji', async () => {
    expect(MAX_SPEECH_CHARS).toBe(1500);
    expect((await speechRoute(d, event({ text: '\u{1F33D}'.repeat(750) }))).statusCode).toBe(200);
  });
  it('requires the producer role', async () => {
    const e = event(); (e.requestContext as unknown as { authorizer: Record<string, string> }).authorizer.roles = 'reviewer';
    await expect(speechRoute(d, e)).rejects.toMatchObject({ name: 'Forbidden' });
  });
  it('logs only the conversation id, character count, voice and duration', async () => {
    await speechRoute(d, event());
    expect(log.info).toHaveBeenCalledTimes(1);
    const [, fields] = log.info.mock.calls[0]!;
    expect(Object.keys(fields).sort()).toEqual(['chars', 'conversation_id', 'duration_ms', 'voice']);
    expect(fields).toMatchObject({ conversation_id: cid, chars: secret.length, voice: 'Lupe' });
    expect(JSON.stringify([log.info.mock.calls, log.warn.mock.calls, log.error.mock.calls])).not.toContain('parcela');
  });
});
