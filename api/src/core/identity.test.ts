import type { APIGatewayProxyEvent } from 'aws-lambda';
import { describe, expect, it } from 'vitest';
import {
  Forbidden,
  Unauthorized,
  requireRole,
  resolveCaller,
  resolveIdentity,
  type Identity,
} from './identity.js';
import { makeEvent } from './testing.js';

/**
 * Identity contract (#11), seam 2: the one identity-resolution function and role gating. The chat
 * routes' use of it (401 on every route, the resolved id reaching the agent, a producer id in the
 * body rejected with 400) is covered in chat.test.ts; this file covers the function itself, the
 * roles, and the 403.
 */

describe('resolveIdentity', () => {
  it('throws Unauthorized when the authorizer context is missing', () => {
    expect(() => resolveIdentity(makeEvent({ producerId: null }))).toThrow(Unauthorized);
  });

  it('throws Unauthorized when there is no user id', () => {
    // A context with roles but no userId is not a caller we can name.
    expect(() => resolveIdentity(makeEvent({ producerId: null, roles: ['reviewer'] }))).toThrow(Unauthorized);
  });

  it('resolves a reviewer with its user id and role, and no producer id', async () => {
    const id = await resolveIdentity(makeEvent({ producerId: null, userId: 'rev-1', roles: ['reviewer'] }));
    expect(id).toEqual({ userId: 'rev-1', roles: ['reviewer'] });
    expect(id.producerId).toBeUndefined();
  });

  it('parses comma-separated roles and keeps only the known ones', async () => {
    const id = await resolveIdentity(makeEvent({ producerId: null, userId: 'u', roles: 'reviewer, admin, wizard' }));
    expect(id.roles).toEqual(['reviewer', 'admin']);
  });

  it('carries the producer id only for a caller with the producer role', async () => {
    const producer = await resolveIdentity(
      makeEvent({ userId: 'u-prod', roles: ['producer'], producerId: 'producer-a' }),
    );
    expect(producer).toEqual({ userId: 'u-prod', roles: ['producer'], producerId: 'producer-a' });

    // An admin whose context happens to carry a producerId does not get one in the identity.
    const admin = await resolveIdentity(makeEvent({ userId: 'u-admin', roles: ['admin'], producerId: 'producer-a' }));
    expect(admin.producerId).toBeUndefined();
  });

  it('never reads identity from the body, path or query string', async () => {
    const event = {
      body: JSON.stringify({ producerId: 'producer-evil', userId: 'evil' }),
      pathParameters: { id: 'producer-evil' },
      queryStringParameters: { producerId: 'producer-evil' },
      requestContext: { authorizer: { userId: 'u', roles: 'reviewer' } },
    } as unknown as APIGatewayProxyEvent;
    const id = await resolveIdentity(event);
    expect(id).toEqual({ userId: 'u', roles: ['reviewer'] });
  });
});

describe('requireRole', () => {
  const reviewer: Identity = { userId: 'rev-1', roles: ['reviewer'] };

  it('returns the identity when the role is present', () => {
    expect(requireRole(reviewer, 'reviewer')).toBe(reviewer);
  });

  it('throws Forbidden when the role is missing', () => {
    expect(() => requireRole(reviewer, 'admin')).toThrow(Forbidden);
    expect(() => requireRole(reviewer, 'producer')).toThrow(Forbidden);
  });
});

describe('resolveCaller (producer-id resolver for chat routes)', () => {
  it('returns the producer id for a producer', () => {
    expect(resolveCaller(makeEvent({ producerId: 'producer-a' }))).toBe('producer-a');
  });

  it('throws Unauthorized when the caller cannot be resolved', () => {
    expect(() => resolveCaller(makeEvent({ producerId: null }))).toThrow(Unauthorized);
  });
});
