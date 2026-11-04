import type { APIGatewayProxyEventV2, APIGatewayProxyResultV2 } from 'aws-lambda';

/**
 * Fair Trade USA review API: list records, correct tags and summary, approve.
 * TODO(#27): implement.
 */
export const handler = async (_event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> => {
  return { statusCode: 501, body: JSON.stringify({ message: 'Not implemented yet (#27)' }) };
};
