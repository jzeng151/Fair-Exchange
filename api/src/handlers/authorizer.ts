import { GetSecretValueCommand, SecretsManagerClient } from '@aws-sdk/client-secrets-manager';
import type { APIGatewayAuthorizerResult, APIGatewayRequestAuthorizerEvent } from 'aws-lambda';
import { authorizeDemo, authorizeDemoAdmin, parseAllowList } from '../core/demoAuth.js';

/**
 * REST API Lambda authorizer (REQUEST type) for the sandbox demo: the deployed sign-in stand-in (#11).
 * Env: DEMO_PASSCODE_SECRET_ARN (Secrets Manager secret holding the passcode) and DEMO_PRODUCER_IDS
 * (comma-separated allow-list, generated from eval/scenarios at synth time).
 * DEMO_ROLE=admin makes it the admin authorizer instead: the admin passcode alone, role `admin`, no producer.
 * Each role has its own function, secret and header.
 * Never logs the passcode or the request.
 */

const secrets = new SecretsManagerClient({});
let passcode: Promise<string> | undefined;

async function loadPasscode(): Promise<string> {
  const arn = process.env.DEMO_PASSCODE_SECRET_ARN;
  if (!arn) throw new Error('DEMO_PASSCODE_SECRET_ARN is not set');
  const out = await secrets.send(new GetSecretValueCommand({ SecretId: arn }));
  if (!out.SecretString) throw new Error('The demo passcode secret is empty');
  return out.SecretString;
}

/** Allow every method of this API stage, so API Gateway's cached decision covers the caller's next request. */
// methodArn: arn:aws:execute-api:<region>:<account>:<apiId>/<stage>/<METHOD>/<path...>
function stageWildcard(methodArn: string): string {
  const [apiArn, stage] = methodArn.split('/');
  return `${apiArn}/${stage}/*`;
}

export const handler = async (event: APIGatewayRequestAuthorizerEvent): Promise<APIGatewayAuthorizerResult> => {
  passcode ??= loadPasscode().catch((err) => {
    passcode = undefined; // retry on the next request rather than caching the failure
    throw err;
  });
  const context = process.env.DEMO_ROLE === 'admin'
    ? authorizeDemoAdmin(event.headers, await passcode)
    : authorizeDemo(event.headers, await passcode, parseAllowList(process.env.DEMO_PRODUCER_IDS));
  // API Gateway turns this exact message into a 401.
  if (!context) throw new Error('Unauthorized');
  return {
    principalId: context.userId,
    policyDocument: {
      Version: '2012-10-17',
      Statement: [{ Action: 'execute-api:Invoke', Effect: 'Allow', Resource: stageWildcard(event.methodArn) }],
    },
    context,
  };
};
