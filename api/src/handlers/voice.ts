import type { APIGatewayProxyEvent, EventBridgeEvent } from 'aws-lambda';
import { voiceDeps, voiceRoute, completeVoice, type VoiceDeps } from '../voice/service.js';
import { toErrorResult } from '../core/routes.js';
const log = { info: () => {}, warn: () => {}, error: () => { console.error('Voice request failed'); } };
let cached: VoiceDeps;
const deps = () => cached ??= voiceDeps();
export async function handler(event: APIGatewayProxyEvent) {
  let result;
  try { result = await voiceRoute(deps(), event); } catch (e) { result = toErrorResult(e, { log }, 'voice'); }
  return { statusCode: result.statusCode, body: JSON.stringify(result.body), headers: {
    'content-type': 'application/json', 'cache-control': 'no-store',
    'access-control-allow-origin': process.env.ALLOWED_ORIGIN ?? '', vary: 'Origin' } };
}
export async function completion(event: EventBridgeEvent<string, { TranscriptionJobName?: string }>) {
  try { await completeVoice(deps(), event.detail.TranscriptionJobName ?? ''); }
  catch { throw new Error('Voice completion failed'); } // Lambda retries; never log AWS payloads or transcripts.
}
