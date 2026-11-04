import type { APIGatewayProxyEvent } from 'aws-lambda';
import { describe, expect, it } from 'vitest';
import { Forbidden, Unauthorized, requireRole, resolveIdentity } from './identity.js';

const event = (authorizer: Record<string, unknown> | undefined, extra: Record<string, unknown> = {}) =>
  ({ requestContext: { authorizer }, ...extra }) as unknown as APIGatewayProxyEvent;

describe('resolveIdentity (placeholder until sign-in is decided)', () => {
  it('reads user ID and roles from the authorizer context only', async () => {
    const id = await resolveIdentity(
      event({ userId: 'u1', roles: 'admin, reviewer,bogus' }, {
        headers: { 'x-roles': 'producer' },
        queryStringParameters: { roles: 'producer' },
        body: JSON.stringify({ roles: ['producer'] }),
      }),
    );
    expect(id).toEqual({ user_id: 'u1', roles: ['reviewer', 'admin'] });
  });

  it('sets producer_id only with the producer role', async () => {
    expect(await resolveIdentity(event({ userId: 'u1', roles: 'producer', producerId: 'p1' }))).toEqual({
      user_id: 'u1',
      roles: ['producer'],
      producer_id: 'p1',
    });
    expect(await resolveIdentity(event({ userId: 'u1', roles: 'admin', producerId: 'p1' }))).toEqual({
      user_id: 'u1',
      roles: ['admin'],
    });
  });

  it('rejects a request with no user ID', () => {
    expect(() => resolveIdentity(event(undefined))).toThrow(Unauthorized);
    expect(() => resolveIdentity(event({ roles: 'admin' }))).toThrow(Unauthorized);
  });
});

describe('requireRole', () => {
  it('throws Forbidden without the role', () => {
    expect(() => requireRole({ user_id: 'u', roles: ['reviewer'] }, 'admin')).toThrow(Forbidden);
    expect(() => requireRole({ user_id: 'u', roles: ['admin'] }, 'admin')).not.toThrow();
  });
});
