#!/usr/bin/env node
import { App, BootstraplessSynthesizer } from 'aws-cdk-lib';
import { AgentArtifactsStack, AgentSpikeStack } from '../lib/agent-spike-stack';
import { AthenaSyncStack } from '../lib/athena-sync-stack';
import { FairExchangeStack } from '../lib/fair-exchange-stack';
import { GuardrailStack } from '../lib/guardrail-stack';

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

// Issue #12: the FEX Guardrail in detect mode (synth-only until the agent stack, #5, deploys it)
new GuardrailStack(app, 'FairExchangeGuardrail', { synthesizer: new BootstraplessSynthesizer(), env });

// Spec 28: records table -> S3 -> Glue/Athena. The records table and its stream come from the write-back work (spec 26);
// pass them with -c recordsTableName=... -c recordsTableStreamArn=... (placeholders keep `cdk synth` working).
new AthenaSyncStack(app, 'FairExchangeAthenaSync', {
  synthesizer: new BootstraplessSynthesizer(),
  env,
  recordsTableName: app.node.tryGetContext('recordsTableName') ?? 'unset-records-table',
  recordsTableStreamArn: app.node.tryGetContext('recordsTableStreamArn')
    ?? `arn:aws:dynamodb:${env.region}:000000000000:table/unset-records-table/stream/2026-01-01T00:00:00.000`,
  recordsTableKeyArn: app.node.tryGetContext('recordsTableKeyArn'),
  codeBucketName: app.node.tryGetContext('syncCodeBucket') ?? 'unset-sync-code-bucket',
  codeKey: app.node.tryGetContext('syncCodeKey') ?? 'sync/unset.zip',
});
