import type { APIGatewayProxyEvent } from 'aws-lambda';
import { Logger } from '@aws-lambda-powertools/logger';
import { attachmentDeps, attachmentsRoute, type AttachmentDeps } from '../attachments/service.js';
import { toErrorResult } from '../core/routes.js';
import type { Log } from '../core/types.js';
const logger = new Logger({ serviceName: 'fex-attachments' });
const log: Log = {
  info: (m, f) => logger.info(m, f ?? {}),
  warn: (m, f) => logger.warn(m, f ?? {}),
  error: (m, f) => logger.error(m, f ?? {}),
};
// Service error names and request IDs aid diagnosis without logging payloads, text or file contents.
function failure(error: unknown) {
  const e = error as { name?: string; $metadata?: { requestId?: string } } | null;
  return { error_type: e?.name, service_request_id: e?.$metadata?.requestId };
}
let cached: AttachmentDeps;
const deps = () => cached ??= attachmentDeps(log);
export async function handler(event: APIGatewayProxyEvent) {
  let result;
  try { result = await attachmentsRoute(deps(), event); } catch (e) {
    result = toErrorResult(e, { log }, 'attachments');
    if (result.statusCode === 500) log.error('Attachment service failure', failure(e));
  }
  return { statusCode: result.statusCode, body: JSON.stringify(result.body), headers: {
    'content-type': 'application/json', 'cache-control': 'no-store',
    'access-control-allow-origin': process.env.ALLOWED_ORIGIN ?? '', vary: 'Origin' } };
}
