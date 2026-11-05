import { describe, expect, it } from 'vitest';
import { authorizeSession } from './demoAuth.js';

const secrets = { producer: 'producer-secret', reviewer: 'reviewer-secret', admin: 'admin-secret' };
const allowed = new Set(['P-001']);
describe('sandbox session authorization', () => {
  it('binds the producer credential to the allow-list', () => {
    expect(authorizeSession({ 'x-demo-passcode': secrets.producer, 'x-demo-producer-id': 'P-001' }, secrets, allowed))
      .toEqual({ userId: 'demo:P-001', roles: 'producer', producerId: 'P-001' });
    expect(authorizeSession({ 'x-demo-passcode': secrets.producer, 'x-demo-producer-id': 'P-999' }, secrets, allowed)).toBeNull();
  });
  it('keeps staff roles separate and never supplies a producer identity', () => {
    expect(authorizeSession({ 'X-Demo-Reviewer-Passcode': secrets.reviewer }, secrets, allowed))
      .toEqual({ userId: 'demo:reviewer', roles: 'reviewer' });
    expect(authorizeSession({ 'x-demo-admin-passcode': secrets.admin }, secrets, allowed))
      .toEqual({ userId: 'demo:admin', roles: 'admin' });
    expect(authorizeSession({ 'x-demo-reviewer-passcode': secrets.admin }, secrets, allowed)).toBeNull();
    expect(authorizeSession({ 'x-demo-admin-passcode': secrets.producer }, secrets, allowed)).toBeNull();
  });
  it('rejects ambiguous, missing and empty credentials', () => {
    expect(authorizeSession({ 'x-demo-reviewer-passcode': secrets.reviewer, 'x-demo-admin-passcode': secrets.admin }, secrets, allowed)).toBeNull();
    expect(authorizeSession({}, secrets, allowed)).toBeNull();
    expect(authorizeSession({ 'x-demo-reviewer-passcode': '' }, { ...secrets, reviewer: '' }, allowed)).toBeNull();
  });
});
