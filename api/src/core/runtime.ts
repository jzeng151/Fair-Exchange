import { randomUUID } from 'node:crypto';
import { Logger } from '@aws-lambda-powertools/logger';
import { AgentCoreClient } from './agent.js';
import { DynamoConversationStore } from './store.js';
import { DEFAULT_LOCK_TTL_MS, type Deps, type Log } from './types.js';

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`Missing environment variable ${name}`);
  return value;
};

/** Builds the real dependencies from environment variables. Called once per cold start. */
export function buildDeps(): Deps {
  // Powertools logs the fields we pass. Callers never pass message or answer text.
  const logger = new Logger({ serviceName: 'fex-chat' });
  const log: Log = {
    info: (m, f) => logger.info(m, f ?? {}),
    warn: (m, f) => logger.warn(m, f ?? {}),
    error: (m, f) => logger.error(m, f ?? {}),
  };
  return {
    store: new DynamoConversationStore(required('CONVERSATIONS_TABLE')),
    agent: new AgentCoreClient(required('AGENT_RUNTIME_ARN')),
    log,
    now: () => Date.now(),
    newId: () => randomUUID(),
    lockTtlMs: DEFAULT_LOCK_TTL_MS,
  };
}

/** The inactivity period is configuration; the spec leaves the value undecided. */
export const inactivityMs = (): number => Number(required('INACTIVITY_MINUTES')) * 60 * 1000;
