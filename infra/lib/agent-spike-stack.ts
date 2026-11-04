import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from 'aws-cdk-lib';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import type { Construct } from 'constructs';

/**
 * Issue #4 spike: a minimal Strands agent on AgentCore Runtime, deployed with CDK.
 *
 * Two small stacks, so the spike works with the bootstrapless setup (no CDK assets):
 *   1. FairExchangeAgentArtifacts: a private bucket for the agent's code zip
 *   2. FairExchangeAgentSpike: the execution role and the AgentCore Runtime that runs the zip
 * `deploy-agent-spike.sh` builds the zip, uploads it and deploys both. `destroy-agent-spike.sh` removes them.
 * #5 folds the runtime into the main stack.
 */

/** Claude via Bedrock, US inference profile only (data stays in US regions). */
export const AGENT_MODEL = 'anthropic.claude-haiku-5-5';
const US_REGIONS = ['us-east-1', 'us-east-2', 'us-west-2'];

export class AgentArtifactsStack extends Stack {
  readonly bucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);
    this.bucket = new s3.Bucket(this, 'AgentCode', {
      encryption: s3.BucketEncryption.S3_MANAGED, // spike: avoids a KMS key's monthly charge; #5 uses KMS
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      versioned: false,
      lifecycleRules: [{ expiration: Duration.days(7) }], // zips are rebuilt on every deploy
      removalPolicy: RemovalPolicy.DESTROY, // the destroy script empties it first
    });
    new CfnOutput(this, 'AgentCodeBucket', { value: this.bucket.bucketName });
  }
}

export interface AgentSpikeStackProps extends StackProps {
  codeBucketName: string;
  codeKey: string;
}

export class AgentSpikeStack extends Stack {
  constructor(scope: Construct, id: string, props: AgentSpikeStackProps) {
    super(scope, id, props);
    const { account, region } = this;

    // Least privilege: only what AgentCore Runtime needs, and only the one Claude model via US profiles.
    const role = new iam.Role(this, 'AgentExecutionRole', {
      assumedBy: new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com', {
        conditions: { StringEquals: { 'aws:SourceAccount': account } },
      }),
      description: 'Fair Exchange agent spike (#4): AgentCore Runtime execution role',
    });
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'InvokeClaudeUsProfileOnly',
      actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
      resources: [
        `arn:aws:bedrock:${region}:${account}:inference-profile/us.${AGENT_MODEL}*`,
        ...US_REGIONS.map((r) => `arn:aws:bedrock:${r}::foundation-model/${AGENT_MODEL}*`),
      ],
    }));
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'ReadAgentCode',
      actions: ['s3:GetObject'],
      resources: [`arn:aws:s3:::${props.codeBucketName}/${props.codeKey}`],
    }));
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'RuntimeLogs',
      actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogStreams'],
      resources: [`arn:aws:logs:${region}:${account}:log-group:/aws/bedrock-agentcore/runtimes/*`],
    }));
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'DescribeLogGroups',
      actions: ['logs:DescribeLogGroups'],
      resources: [`arn:aws:logs:${region}:${account}:log-group:*`],
    }));
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'Traces',
      actions: ['xray:PutTraceSegments', 'xray:PutTelemetryRecords', 'xray:GetSamplingRules', 'xray:GetSamplingTargets'],
      resources: ['*'], // X-Ray does not support resource-level permissions
    }));
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'Metrics',
      actions: ['cloudwatch:PutMetricData'],
      resources: ['*'],
      conditions: { StringEquals: { 'cloudwatch:namespace': 'bedrock-agentcore' } },
    }));
    role.addToPolicy(new iam.PolicyStatement({
      sid: 'WorkloadIdentity',
      actions: ['bedrock-agentcore:GetWorkloadAccessToken', 'bedrock-agentcore:GetWorkloadAccessTokenForJWT', 'bedrock-agentcore:GetWorkloadAccessTokenForUserId'],
      resources: [
        `arn:aws:bedrock-agentcore:${region}:${account}:workload-identity-directory/default`,
        `arn:aws:bedrock-agentcore:${region}:${account}:workload-identity-directory/default/workload-identity/*`,
      ],
    }));

    const runtime = new agentcore.CfnRuntime(this, 'HelloRuntime', {
      agentRuntimeName: 'fair_exchange_hello',
      description: 'Fair Exchange #4 spike: Strands agent reading producer_id from invocation_state',
      roleArn: role.roleArn,
      networkConfiguration: { networkMode: 'PUBLIC' },
      protocolConfiguration: 'HTTP',
      agentRuntimeArtifact: {
        codeConfiguration: {
          code: { s3: { bucket: props.codeBucketName, prefix: props.codeKey } },
          // opentelemetry-instrument switches on AgentCore Observability (traces); plain main.py emits none
          entryPoint: ['opentelemetry-instrument', 'main.py'],
          runtime: 'PYTHON_3_12',
        },
      },
      environmentVariables: { AWS_REGION: region },
    });
    runtime.node.addDependency(role);

    new CfnOutput(this, 'AgentRuntimeArn', { value: runtime.attrAgentRuntimeArn });
    new CfnOutput(this, 'AgentRoleName', { value: role.roleName });
  }
}
