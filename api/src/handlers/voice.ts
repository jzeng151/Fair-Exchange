import type { APIGatewayProxyEvent, EventBridgeEvent } from 'aws-lambda';
import { Logger } from '@aws-lambda-powertools/logger';
import { voiceDeps, voiceRoute, completeVoice, type VoiceDeps } from '../voice/service.js';
import { toErrorResult } from '../core/routes.js';
import type { Log } from '../core/types.js';
const logger = new Logger({ serviceName: 'fex-voice' });
const log: Log = {
  info: (m, f) => logger.info(m, f ?? {}),
  warn: (m, f) => logger.warn(m, f ?? {}),
  error: (m, f) => logger.error(m, f ?? {}),
};
// Service error names and request IDs aid diagnosis without logging payloads or text.
function failure(error: unknown) {
  const e = error as { name?: string; $metadata?: { requestId?: string } } | null;
  return { error_type: e?.name, service_request_id: e?.$metadata?.requestId };
}
let cached: VoiceDeps;
const deps = () => cached ??= voiceDeps();
export async function handler(event: APIGatewayProxyEvent) {
  let result;
  try { result = await voiceRoute(deps(), event); } catch (e) {
    result = toErrorResult(e, { log }, 'voice');
    if (result.statusCode === 500) log.error('Voice service failure', failure(e));
  }
  return { statusCode: result.statusCode, body: JSON.stringify(result.body), headers: {
    'content-type': 'application/json', 'cache-control': 'no-store',
    'access-control-allow-origin': process.env.ALLOWED_ORIGIN ?? '', vary: 'Origin' } };
}
export async function completion(event: EventBridgeEvent<string, { TranscriptionJobName?: string }>) {
  try { await completeVoice(deps(), event.detail.TranscriptionJobName ?? ''); }
  catch (e) {
    log.error('Voice completion failure', failure(e));
    throw new Error('Voice completion failed'); // Lambda retries; never log AWS payloads or transcripts.
  }
}
