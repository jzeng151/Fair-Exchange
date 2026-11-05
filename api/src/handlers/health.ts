import type { APIGatewayProxyResult } from 'aws-lambda';

/** GET /health (#25, spec 05): no sign-in; returns the deployed version for the deploy smoke check. */
export const handler = async (): Promise<APIGatewayProxyResult> => ({
  statusCode: 200,
  headers: {
    'content-type': 'application/json',
    ...(process.env.ALLOWED_ORIGIN ? { 'access-control-allow-origin': process.env.ALLOWED_ORIGIN } : {}),
  },
  body: JSON.stringify({ status: 'ok', version: process.env.FEX_VERSION ?? 'unknown' }),
});
