export const MAX_MESSAGE_CHARS = 4000;

/** Thrown for request bodies the API refuses. Handlers return 400. */
export class BadRequest extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BadRequest';
  }
}

/** Identity and conversation ID are never accepted from a client, at any depth we check. */
const FORBIDDEN_KEYS = new Set(['producerid', 'producer_id', 'conversationid', 'conversation_id']);

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export const isConversationId = (id: string | undefined): id is string =>
  typeof id === 'string' && UUID_V4.test(id);

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

function parseObject(body: string | null | undefined): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body ?? '');
  } catch {
    throw new BadRequest('Body must be a JSON object');
  }
  if (!isPlainObject(parsed)) throw new BadRequest('Body must be a JSON object');
  return parsed;
}

function rejectUnknown(obj: Record<string, unknown>, allowed: string[]): void {
  for (const key of Object.keys(obj)) {
    if (FORBIDDEN_KEYS.has(key.toLowerCase())) {
      throw new BadRequest('Producer and conversation IDs cannot be set by the client');
    }
    if (!allowed.includes(key)) throw new BadRequest(`Unknown field: ${key}`);
  }
}

export function parseMessageBody(body: string | null | undefined): { text: string } {
  const obj = parseObject(body);
  rejectUnknown(obj, ['text']);
  const { text } = obj;
  if (typeof text !== 'string' || text.length < 1 || text.length > MAX_MESSAGE_CHARS) {
    throw new BadRequest(`text must be 1 to ${MAX_MESSAGE_CHARS} characters`);
  }
  return { text };
}

export function parseActionBody(body: string | null | undefined): {
  name: string;
  args: Record<string, unknown>;
} {
  const obj = parseObject(body);
  rejectUnknown(obj, ['action', 'args']);
  const { action, args = {} } = obj;
  if (typeof action !== 'string' || action.length === 0) {
    throw new BadRequest('action must be a non-empty string');
  }
  if (!isPlainObject(args)) throw new BadRequest('args must be an object');
  rejectUnknown(args, Object.keys(args).filter((k) => !FORBIDDEN_KEYS.has(k.toLowerCase())));
  return { name: action, args };
}

/** POST /conversations takes no body fields. An empty body is fine. */
export function parseStartBody(body: string | null | undefined): void {
  if (body === null || body === undefined || body.trim() === '') return;
  rejectUnknown(parseObject(body), []);
}
