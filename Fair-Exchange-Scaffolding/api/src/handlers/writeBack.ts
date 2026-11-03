import type { APIGatewayProxyEventV2, APIGatewayProxyResultV2 } from 'aws-lambda';

/**
 * On consent: Comprehend DetectPiiEntities to FLAG (never redact), then write exactly one record (idempotent).
 * TODO(#26): implement.
 */
export const handler = async (_event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> => {
  return { statusCode: 501, body: JSON.stringify({ message: 'Not implemented yet (#26)' }) };
};
