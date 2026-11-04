import { createHash, timingSafeEqual } from 'node:crypto';

/**
 * The deployed sign-in stand-in (#11, decided 2026-11-04 for the sandbox demo): a shared passcode plus a
 * producer chosen from a fixed allow-list of the eval scenario producers (synthetic data only).
 * API Gateway's Lambda authorizer runs this; its result becomes `requestContext.authorizer`, which the
 * one identity-resolution function (identity.ts) reads. Production sign-in (Okta) replaces this.
 */

export const PRODUCER_HEADER = 'x-demo-producer-id';
export const PASSCODE_HEADER = 'x-demo-passcode';

/** What the authorizer hands API Gateway as context; flat strings, as the REST API requires. */
export interface DemoContext {
  [key: string]: string;
  producerId: string;
  userId: string;
  roles: string;
}

/** Header lookup is case-insensitive: browsers and API Gateway may change the case. */
export function header(headers: Record<string, string | undefined> | null | undefined, name: string): string | undefined {
  if (!headers) return undefined;
  for (const [k, v] of Object.entries(headers)) if (k.toLowerCase() === name && typeof v === 'string') return v;
  return undefined;
}

const digest = (s: string) => createHash('sha256').update(s, 'utf8').digest();

/** Constant-time comparison; hashing first makes the lengths equal. */
export function passcodeMatches(given: string, expected: string): boolean {
  return expected.length > 0 && timingSafeEqual(digest(given), digest(expected));
}

/** Parses the comma-separated allow-list; an empty list allows nobody. */
export function parseAllowList(raw: string | undefined): Set<string> {
  return new Set((raw ?? '').split(',').map((s) => s.trim()).filter(Boolean));
}

/**
 * The decision. Returns the identity context, or null to reject (API Gateway answers 401).
 * The passcode is checked before the producer, so a caller without it learns nothing about the list.
 */
export function authorizeDemo(
  headers: Record<string, string | undefined> | null | undefined,
  passcode: string,
  allowed: Set<string>,
): DemoContext | null {
  const given = header(headers, PASSCODE_HEADER);
  if (given === undefined || !passcodeMatches(given, passcode)) return null;
  const producerId = header(headers, PRODUCER_HEADER)?.trim();
  if (!producerId || !allowed.has(producerId)) return null;
  return { producerId, userId: `demo:${producerId}`, roles: 'producer' };
}
