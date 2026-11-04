import type { APIGatewayProxyEventV2, APIGatewayProxyResultV2 } from 'aws-lambda';

/**
 * Dashboard data: usage, challenge trends, issues needing attention, AI footprint.
 * TODO(#29): implement.
 */
export const handler = async (_event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> => {
  return { statusCode: 501, body: JSON.stringify({ message: 'Not implemented yet (#29)' }) };
};
