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

export type Role = 'producer' | 'reviewer' | 'admin';

/** The caller as the identity-resolution function returns it (#11 spec). */
export interface Identity {
  userId: string;
  roles: Role[];
  /** Present only with the `producer` role. */
  producerId?: string;
}

/** Thrown when the caller is identified but lacks the route's role. Handlers return 403. */
export class Forbidden extends Error {
  constructor() {
    super('Forbidden');
    this.name = 'Forbidden';
  }
}

export type IdentityFullResolver = (event: APIGatewayProxyEvent) => Promise<Identity> | Identity;

const ROLES: readonly string[] = ['producer', 'reviewer', 'admin'];

/**
 * Placeholder, like `resolveCaller`: reads `userId`, `roles` (comma separated) and `producerId` from the
 * API Gateway authorizer context, never from the request. Replace it when the sign-in method is chosen.
 */
export const resolveIdentity: IdentityFullResolver = (event) => {
  const ctx = event.requestContext?.authorizer;
  const userId = ctx?.userId;
  if (typeof userId !== 'string' || userId.length === 0) throw new Unauthorized();
  const roles = (typeof ctx?.roles === 'string' ? ctx.roles.split(',') : [])
    .map((r: string) => r.trim())
    .filter((r: string): r is Role => ROLES.includes(r));
  const identity: Identity = { userId, roles };
  if (roles.includes('producer') && typeof ctx?.producerId === 'string' && ctx.producerId.length > 0) {
    identity.producerId = ctx.producerId;
  }
  return identity;
};

/** Returns the identity if it has the role, otherwise throws Forbidden. */
export function requireRole(identity: Identity, role: Role): Identity {
  if (!identity.roles.includes(role)) throw new Forbidden();
  return identity;
}
