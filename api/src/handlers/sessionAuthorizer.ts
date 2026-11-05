import { GetSecretValueCommand, SecretsManagerClient } from '@aws-sdk/client-secrets-manager';
import type { APIGatewayAuthorizerResult, APIGatewayRequestAuthorizerEvent } from 'aws-lambda';
import { authorizeSession, parseAllowList } from '../core/demoAuth.js';

const client = new SecretsManagerClient({});
const cache = new Map<string, Promise<string>>();
function secret(arn: string | undefined): Promise<string> {
  if (!arn) return Promise.resolve('');
  if (!cache.has(arn)) cache.set(arn, client.send(new GetSecretValueCommand({ SecretId: arn }))
    .then((r) => r.SecretString ?? '').catch((error) => { cache.delete(arn); throw error; }));
  return cache.get(arn)!;
}

/** Sandbox-only role credentials. No secrets or request headers are logged. */
export async function handler(event: APIGatewayRequestAuthorizerEvent): Promise<APIGatewayAuthorizerResult> {
  const [producer, reviewer, admin] = await Promise.all([
    secret(process.env.PRODUCER_SECRET_ARN), secret(process.env.REVIEWER_SECRET_ARN), secret(process.env.ADMIN_SECRET_ARN),
  ]);
  const context = authorizeSession(event.headers, { producer, reviewer, admin }, parseAllowList(process.env.DEMO_PRODUCER_IDS));
  if (!context) throw new Error('Unauthorized');
  return { principalId: context.userId, context, policyDocument: {
    Version: '2012-10-17', Statement: [{ Action: 'execute-api:Invoke', Effect: 'Allow', Resource: event.methodArn }],
  } };
}
