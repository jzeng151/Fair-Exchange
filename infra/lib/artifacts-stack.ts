import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
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
 * `<stackName>Artifacts` (docs/specs/05-cdk-stack.md): files the application stack reads while it is created
 * or updated, uploaded by infra/deploy.sh between the two stacks. Holds:
 *   - the artifacts key (customer-managed KMS, rotated) and the artifacts bucket encrypted with it;
 *   - standards clause documents under `clauses/` (#17), and the agent code zip (#5, next).
 * Both are kept when the stack is deleted. Clause documents expire after `docsTtlDays`, so a kept bucket
 * empties itself. The application data key (vectors, tables, logs) is in the application stack.
 */
export class ArtifactsStack extends Stack {
  constructor(scope: Construct, id: string, props: ArtifactsStackProps) {
    super(scope, id, props);

    // Logical ID kept from the first deploy, so the existing key is not replaced
    const key = new kms.Key(this, 'DataKey', {
      description: 'Fair Exchange build artifacts: standards clause documents and agent code',
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });

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
    new CfnOutput(this, 'ArtifactsKeyArn', { value: key.keyArn });
  }
}
