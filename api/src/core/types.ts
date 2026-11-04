/** Shapes shared by the chat handlers and the inactivity sweep (#25). */

export type ConversationStatus = 'open' | 'closed';

export interface Conversation {
  conversationId: string;
  producerId: string;
  /** Epoch milliseconds. */
  createdAt: number;
  status: ConversationStatus;
  closedAt?: number;
  lastActivityAt: number;
  /** Epoch ms. A turn is in progress while this is in the future. */
  lockExpiresAt?: number;
  /** Identifies the turn holding the lock. Only that turn may release it. */
  lockToken?: string;
}

/** What the agent runtime receives. producerId always comes from the resolved identity. */
export type AgentRequest =
  | { kind: 'start' | 'resume' | 'inactivity_close'; producerId: string; conversationId: string }
  | { kind: 'message'; producerId: string; conversationId: string; text: string }
  | {
      kind: 'action';
      producerId: string;
      conversationId: string;
      action: { name: string; args: Record<string, unknown> };
    };

/**
 * One event from the agent stream (#13 spec). Passed through unchanged, so only
 * the fields the handler reads are typed.
 */
export interface AgentEvent {
  type: string;
  seq?: number;
  step?: string;
  [key: string]: unknown;
}

export interface AgentClient {
  /**
   * Streams the agent's events for start, message, action and inactivity_close.
   * Aborting `signal` must cancel the underlying call.
   */
  stream(request: AgentRequest, signal?: AbortSignal): AsyncIterable<AgentEvent>;
  /** Returns the agent's resume object (step, allowed actions, latest answer, history). */
  resume(request: AgentRequest): Promise<Record<string, unknown> & { step?: string }>;
}

export interface ConversationStore {
  /** Creates an open conversation. Fails if the ID already exists. */
  create(conversation: Conversation): Promise<void>;
  get(conversationId: string): Promise<Conversation | undefined>;
  /** The producer's conversations, newest first. */
  listByProducer(producerId: string): Promise<Conversation[]>;
  /**
   * Takes the turn lock if no unexpired lock exists and the conversation is open,
   * recording `token` as the holder. Sets last_activity_at only when `touchActivity` is true.
   */
  acquireLock(
    conversationId: string,
    now: number,
    lockExpiresAt: number,
    touchActivity: boolean,
    token: string,
  ): Promise<boolean>;
  /** Releases the lock only if `token` still holds it. Otherwise does nothing. */
  releaseLock(conversationId: string, token: string): Promise<void>;
  markClosed(conversationId: string, now: number): Promise<void>;
  /** All open conversations. Used only by the sweep. */
  listOpen(): Promise<Conversation[]>;
}

/** Log calls take ids, routes, statuses and timings. Never message or answer text. */
export interface Log {
  info(message: string, fields?: Record<string, unknown>): void;
  warn(message: string, fields?: Record<string, unknown>): void;
  error(message: string, fields?: Record<string, unknown>): void;
}

export interface Deps {
  store: ConversationStore;
  agent: AgentClient;
  log: Log;
  now: () => number;
  newId: () => string;
  /** Hard limit on one agent call. Must be shorter than `lockTtlMs`. */
  turnTimeoutMs: number;
  /** Turn lock lifetime. Slightly longer than `turnTimeoutMs`. */
  lockTtlMs: number;
}

/** The streaming routes' Lambda and integration timeout (#25 spec). */
export const LAMBDA_TIMEOUT_MS = 5 * 60 * 1000;
/** Agent calls stop 10s early, so the handler can still send error/done and release the lock. */
export const TURN_TIMEOUT_MS = LAMBDA_TIMEOUT_MS - 10 * 1000;
/** Outlives any handler, so only a crashed handler's lock is ever freed by expiry. */
export const DEFAULT_LOCK_TTL_MS = LAMBDA_TIMEOUT_MS + 30 * 1000;
