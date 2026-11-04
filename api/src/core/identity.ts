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
