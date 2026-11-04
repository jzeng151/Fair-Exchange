import { Conflict, beginTurn, boundedResume, boundedStream, endTurn } from './turn.js';
import type { Deps, Conversation } from './types.js';

export interface SweepResult {
  closedIdle: number;
  closedByReconcile: number;
  skipped: number;
}

/**
 * Inactivity sweep (#25 spec). Closes idle open conversations via `inactivity_close`,
 * and reconciles open, non-idle ones whose agent state is already `closed`.
 * Never changes last_activity_at.
 *
 * @param inactivityMs the inactivity period (a configuration value; not decided in the spec)
 */
export async function runSweep(deps: Deps, inactivityMs: number): Promise<SweepResult> {
  const result: SweepResult = { closedIdle: 0, closedByReconcile: 0, skipped: 0 };
  const started = deps.now();
  const open = await deps.store.listOpen();

  for (const candidate of open) {
    try {
      if (started - candidate.lastActivityAt >= inactivityMs) {
        const closed = await closeIfStillIdle(deps, candidate, inactivityMs);
        if (closed === 'closed') result.closedIdle++;
        else if (closed === 'skipped') result.skipped++;
      } else if (await reconcile(deps, candidate)) {
        result.closedByReconcile++;
      }
    } catch {
      // One bad conversation must not stop the sweep. The next run retries it.
      deps.log.error('sweep failed for conversation', {
        conversationId: candidate.conversationId,
        producerId: candidate.producerId,
      });
      result.skipped++;
    }
  }
  deps.log.info('sweep finished', { ...result, openCount: open.length, ms: deps.now() - started });
  return result;
}

async function closeIfStillIdle(
  deps: Deps,
  candidate: Conversation,
  inactivityMs: number,
): Promise<'closed' | 'skipped' | 'open'> {
  // The lock is taken without touching activity, so the sweep never makes a conversation look active.
  let lease;
  try {
    lease = await beginTurn(deps, candidate, false);
  } catch (err) {
    if (err instanceof Conflict) return 'skipped';
    throw err;
  }
  try {
    // Re-check under the lock: a turn may have been accepted since the scan.
    const fresh = await deps.store.get(candidate.conversationId);
    if (!fresh || fresh.status !== 'open' || deps.now() - fresh.lastActivityAt < inactivityMs) {
      return 'skipped';
    }
    let closed = false;
    for await (const event of boundedStream(deps, {
      kind: 'inactivity_close',
      producerId: fresh.producerId,
      conversationId: fresh.conversationId,
    })) {
      if (event.type === 'step' && event.step === 'closed') closed = true;
    }
    if (!closed) return 'open';
    await deps.store.markClosed(fresh.conversationId, deps.now());
    return 'closed';
  } finally {
    await endTurn(deps, lease);
  }
}

async function reconcile(deps: Deps, candidate: Conversation): Promise<boolean> {
  // A live turn will mark the conversation closed itself.
  if (candidate.lockExpiresAt !== undefined && candidate.lockExpiresAt > deps.now()) return false;
  // Bounded, so a stalled agent is skipped (and retried next run) instead of blocking the sweep.
  const resumed = await boundedResume(deps, {
    kind: 'resume',
    producerId: candidate.producerId,
    conversationId: candidate.conversationId,
  });
  if (resumed.step !== 'closed') return false;
  await deps.store.markClosed(candidate.conversationId, deps.now());
  return true;
}
