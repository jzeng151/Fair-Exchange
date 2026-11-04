import type { APIGatewayProxyEvent } from 'aws-lambda';

/** Thrown when the caller cannot be identified. Handlers return 401. */
export class Unauthorized extends Error {
  constructor() {
    super('Unauthorized');
    this.name = 'Unauthorized';
  }
}

/**
 * The identity-resolution function (#11 spec). Every route calls it first, and
 * nothing else reads identity from a request. Takes the API request, returns the
 * producer ID or throws Unauthorized.
 */
export type IdentityResolver = (event: APIGatewayProxyEvent) => Promise<string> | string;

/**
 * Placeholder until FTUSA decides how callers sign in (not decided in the #11 spec).
 * Reads the producer ID that the API Gateway authorizer put in the request context.
 * It never reads the body, path, query string or headers. Replace this function
 * when the sign-in method is chosen; no handler changes.
 */
export const resolveCaller: IdentityResolver = (event) => {
  const producerId = event.requestContext?.authorizer?.producerId;
  if (typeof producerId !== 'string' || producerId.length === 0) {
    throw new Unauthorized();
  }
  return producerId;
};

/** Thrown when the caller is identified but lacks the route's role. Handlers return 403. */
export class Forbidden extends Error {
  constructor() {
    super('Forbidden');
    this.name = 'Forbidden';
  }
}

export type Role = 'producer' | 'reviewer' | 'admin';

/** The caller's identity (#11 spec). `producer_id` is present only with the `producer` role. */
export interface CallerIdentity {
  user_id: string;
  roles: Role[];
  producer_id?: string;
}

/** Identity resolution for routes that check roles (#11 spec). Throws Unauthorized when unidentified. */
export type RoleResolver = (event: APIGatewayProxyEvent) => Promise<CallerIdentity> | CallerIdentity;

const ROLES: readonly Role[] = ['producer', 'reviewer', 'admin'];

/**
 * Placeholder, like `resolveCaller`, until FTUSA decides how callers sign in (not decided in the
 * #11 spec). Reads `userId` and `roles` (comma-separated, because authorizer context values are
 * strings) from the API Gateway authorizer context only, never from the body, path, query string
 * or headers. Replace this function when the sign-in method is chosen; no handler changes.
 */
export const resolveIdentity: RoleResolver = (event) => {
  const ctx = event.requestContext?.authorizer;
  const userId = ctx?.userId;
  if (typeof userId !== 'string' || userId.length === 0) throw new Unauthorized();
  const given = typeof ctx?.roles === 'string' ? ctx.roles.split(',').map((s: string) => s.trim()) : [];
  const roles = ROLES.filter((r) => given.includes(r));
  const producerId = ctx?.producerId;
  return roles.includes('producer') && typeof producerId === 'string' && producerId.length > 0
    ? { user_id: userId, roles, producer_id: producerId }
    : { user_id: userId, roles };
};

/** Throws Forbidden (403) unless the caller has `role`. */
export function requireRole(identity: CallerIdentity, role: Role): void {
  if (!identity.roles.includes(role)) throw new Forbidden();
}
