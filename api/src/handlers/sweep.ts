import { buildDeps, inactivityMs } from '../core/runtime.js';
import { runSweep } from '../core/sweep.js';

/** Scheduled every 15 minutes (#25). Closes idle conversations and reconciles closed ones. */
export const handler = async () => runSweep(buildDeps(), inactivityMs());
