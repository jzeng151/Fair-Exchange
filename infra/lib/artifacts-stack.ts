import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as s3 from 'aws-cdk-lib/aws-s3';
import type { Construct } from 'constructs';

/** Prefix of the standards clause documents (#17) in the artifacts bucket. */
export const CLAUSE_DOCS_PREFIX = 'clauses/';

export interface ArtifactsStackProps extends StackProps {
  /** Days before an uploaded clause document expires. infra/deploy.sh re-uploads every document on each deploy. */
  docsTtlDays: number;
}

/**
 * Files the main stack needs to exist before it is created (issue #5). The stacks use the bootstrapless
 * synthesizer (no CDK assets), so infra/deploy.sh deploys this stack, uploads the files, then deploys
 * `FairExchange`. Holds:
 *   - the application data key (customer-managed KMS, rotated), for these files and the Knowledge Base vectors;
 *   - the artifacts bucket: standards clause documents under `clauses/` (#17), later the agent code zip.
 * Both are kept when the stack is deleted. Clause documents expire after `docsTtlDays`, so a kept bucket
 * empties itself.
 */
export class ArtifactsStack extends Stack {
  constructor(scope: Construct, id: string, props: ArtifactsStackProps) {
    super(scope, id, props);

    const key = new kms.Key(this, 'DataKey', {
      description: 'Fair Exchange application data: build artifacts and Knowledge Base vectors',
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    // S3 Vectors maintains indexes in the background with its own service principal (S3 Vectors docs,
    // "Using SSE-KMS encryption"); limited to this account's vector buckets and S3 Vectors encryption contexts.
    key.addToResourcePolicy(new iam.PolicyStatement({
      sid: 'AllowS3VectorsIndexing',
      principals: [new iam.ServicePrincipal('indexing.s3vectors.amazonaws.com')],
      actions: ['kms:Decrypt'],
      resources: ['*'],
      conditions: {
        ArnLike: { 'aws:SourceArn': `arn:aws:s3vectors:${this.region}:${this.account}:bucket/*` },
        StringEquals: { 'aws:SourceAccount': this.account },
        'ForAnyValue:StringEquals': { 'kms:EncryptionContextKeys': ['aws:s3vectors:arn', 'aws:s3vectors:resource-id'] },
      },
    }));

    const bucket = new s3.Bucket(this, 'Artifacts', {
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: key,
      bucketKeyEnabled: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      removalPolicy: RemovalPolicy.RETAIN,
      lifecycleRules: [
        { id: 'ExpireClauseDocuments', prefix: CLAUSE_DOCS_PREFIX, expiration: Duration.days(props.docsTtlDays) },
        { id: 'AbortUploads', abortIncompleteMultipartUploadAfter: Duration.days(1) },
      ],
    });

    new CfnOutput(this, 'ArtifactsBucketName', { value: bucket.bucketName });
    new CfnOutput(this, 'DataKeyArn', { value: key.keyArn });
  }
}
