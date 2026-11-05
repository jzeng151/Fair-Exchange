import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { PollyClient, SynthesizeSpeechCommand, type LanguageCode, type VoiceId } from '@aws-sdk/client-polly';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import { loadOwnedConversation } from '../core/ownedConversation.js';
import { MAX_SPEECH_CHARS, parseSpeechBody } from '../core/validate.js';
import { json } from '../core/routes.js';
import type { Log } from '../core/types.js';

export { MAX_SPEECH_CHARS };
export interface SpeechDeps { db: DynamoDBClient; polly: PollyClient; conversations: string; log: Log; clock: () => number }
export function speechDeps(log: Log): SpeechDeps {
  const conversations = process.env.CONVERSATIONS_TABLE;
  if (!conversations) throw new Error('Missing CONVERSATIONS_TABLE');
  return { db: new DynamoDBClient({}), polly: new PollyClient({}), conversations, log, clock: () => Date.now() };
}

/** Chosen from the stored conversation language only, never from the request. */
const VOICES: Record<string, { voice: VoiceId; code: LanguageCode }> = {
  en: { voice: 'Joanna', code: 'en-US' }, es: { voice: 'Lupe', code: 'es-US' }, fr: { voice: 'Lea', code: 'fr-FR' },
};

/** POST /conversations/{id}/speech: open or closed conversations, so earlier replies can still be heard. Nothing is stored. */
export async function speechRoute(d: SpeechDeps, event: APIGatewayProxyEvent) {
  const started = d.clock();
  const conversation = await loadOwnedConversation(d.db, d.conversations, event);
  const { text } = parseSpeechBody(event.body);
  const { voice, code } = VOICES[conversation.language ?? ''] ?? VOICES.en!;
  const result = await d.polly.send(new SynthesizeSpeechCommand({ Text: text, TextType: 'text', VoiceId: voice,
    LanguageCode: code, Engine: 'neural', OutputFormat: 'mp3' }));
  if (!result.AudioStream) throw new Error('Polly returned no audio');
  const audio = Buffer.from(await result.AudioStream.transformToByteArray()).toString('base64');
  d.log.info('Speech synthesized', { conversation_id: conversation.id, chars: text.length, voice, duration_ms: d.clock() - started });
  return json(200, { content_type: 'audio/mpeg', audio });
}
