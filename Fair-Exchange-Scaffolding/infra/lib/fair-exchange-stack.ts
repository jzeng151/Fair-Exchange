import { Stack, type StackProps } from 'aws-cdk-lib';
import type { Construct } from 'constructs';

/**
 * The whole Fair Exchange stack, deployable with one command (issue #5).
 * Add each piece here as its issue lands:
 *   - Data: S3 buckets (encrypted, KMS), Glue database + tables, Athena workgroup        (#28)
 *   - Agent: AgentCore Runtime for FEX + execution role (bedrock:InvokeModel on us. profiles only) (#4)
 *   - Guardrail in detect mode                                                           (#12)
 *   - Knowledge Bases (S3 Vectors, NOT OpenSearch Serverless: it has an always-on cost)    (#16, #17)
 *   - API: API Gateway + Lambdas (chat, write-back, review, analytics), Powertools          (#25–#29)
 *   - Records: DynamoDB table (encrypted), Comprehend permissions                          (#26)
 *   - Web: S3 + CloudFront for the Vue app                                                 (#30–#33)
 *   - Observability: AgentCore Observability / CloudWatch, log retention policy
 * Least-privilege IAM per Lambda and for the AgentCore role. No real producer PII.
 */
export class FairExchangeStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);
  }
}
