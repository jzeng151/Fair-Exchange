#!/usr/bin/env node
import { App, BootstraplessSynthesizer } from 'aws-cdk-lib';
import { AgentArtifactsStack, AgentSpikeStack } from '../lib/agent-spike-stack';
import { FairExchangeStack } from '../lib/fair-exchange-stack';

const app = new App();
const env = { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? 'us-west-2' };
new FairExchangeStack(app, 'FairExchange', { synthesizer: new BootstraplessSynthesizer(), env });

// Issue #4 spike (deploy-agent-spike.sh passes the code location as context; placeholders keep `cdk synth` working)
new AgentArtifactsStack(app, 'FairExchangeAgentArtifacts', { synthesizer: new BootstraplessSynthesizer(), env });
new AgentSpikeStack(app, 'FairExchangeAgentSpike', {
  synthesizer: new BootstraplessSynthesizer(),
  env,
  codeBucketName: app.node.tryGetContext('agentCodeBucket') ?? 'unset-agent-code-bucket',
  codeKey: app.node.tryGetContext('agentCodeKey') ?? 'hello/unset.zip',
});
