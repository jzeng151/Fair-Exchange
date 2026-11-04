import { CfnOutput, RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as s3 from 'aws-cdk-lib/aws-s3';
import type { Construct } from 'constructs';
import { FexGuardrail } from './guardrail';
import { StandardsKnowledgeBase, type StandardsKnowledgeBaseProps } from './standards-kb';

export interface FairExchangeStackProps extends StackProps {
  /** From FairExchangeArtifacts and the clause build; infra/deploy.sh passes them as CDK context. */
  standards: StandardsKnowledgeBaseProps;
}

/**
 * The whole Fair Exchange stack, deployable with one command (issue #5).
 * Add each piece here as its issue lands:
 *   - Data: S3 buckets (encrypted, KMS), Glue database + tables, Athena workgroup        (#28)
 *   - Agent: AgentCore Runtime for FEX + execution role (bedrock:InvokeModel on us. profiles only) (#4)
 *   - Guardrail in detect mode (FexGuardrail; the FEX runtime takes runtimeEnvironment + grantApply) (#12)
 *   - Knowledge Bases (S3 Vectors, NOT OpenSearch Serverless: it has an always-on cost)    (#16, #17: standards done)
 *   - API: API Gateway + Lambdas (chat, write-back, review, analytics), Powertools          (#25–#29)
 *   - Records: DynamoDB table (encrypted), Comprehend permissions                          (#26)
 *   - Web: S3 + CloudFront for the Vue app                                                 (#30–#33)
 *   - Observability: AgentCore Observability / CloudWatch, log retention policy
 * Least-privilege IAM per Lambda and for the AgentCore role. No real producer PII.
 * Files this stack reads at deploy time live in FairExchangeArtifacts (artifacts-stack.ts), deployed first.
 */
export class FairExchangeStack extends Stack {
  constructor(scope: Construct, id: string, props: FairExchangeStackProps) {
    super(scope, id, props);

    // Hosting slice for #5 and #30. Upload only web/dist, never the source/data folders.
    const key = new kms.Key(this, 'WebKey', {
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const bucket = new s3.Bucket(this, 'WebBucket', {
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: key,
      bucketKeyEnabled: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const distribution = new cloudfront.Distribution(this, 'WebDistribution', {
      comment: 'Fair Exchange sandbox scaffold',
      defaultRootObject: 'index.html',
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(bucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        compress: true,
      },
    });
    new CfnOutput(this, 'WebBucketName', { value: bucket.bucketName });
    new CfnOutput(this, 'WebDistributionId', { value: distribution.distributionId });
    new CfnOutput(this, 'WebUrl', { value: `https://${distribution.distributionDomainName}` });

    // #12: the FEX runtime (#4, #5) passes guardrail.runtimeEnvironment and calls guardrail.grantApply(role).
    const guardrail = new FexGuardrail(this, 'FexGuardrail');
    new CfnOutput(this, 'GuardrailId', { value: guardrail.guardrail.attrGuardrailId });
    new CfnOutput(this, 'GuardrailVersion', { value: guardrail.version.attrVersion });

    // Standards grounding (#17): the agent runtime (#4) gets bedrock:Retrieve on it and FEX_STANDARDS_KB_ID
    new StandardsKnowledgeBase(this, 'StandardsKnowledgeBase', props.standards);
  }
}
