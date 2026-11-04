import type { APIGatewayProxyEventV2, APIGatewayProxyResultV2 } from 'aws-lambda';

/**
 * POST /chat. producerId comes from the authenticated identity, never the request body.
 * TODO(#25): implement.
 */
export const handler = async (_event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> => {
  return { statusCode: 501, body: JSON.stringify({ message: 'Not implemented yet (#25)' }) };
};
