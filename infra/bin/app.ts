#!/usr/bin/env node
import { App, BootstraplessSynthesizer } from 'aws-cdk-lib';
import { AgentArtifactsStack, AgentSpikeStack } from '../lib/agent-spike-stack';
import { AnalyticsQueriesStack } from '../lib/analytics-queries-stack';
import { AthenaSyncStack } from '../lib/athena-sync-stack';
import { FairExchangeStack } from '../lib/fair-exchange-stack';
import { ArtifactsStack } from '../lib/artifacts-stack';
import { FairExchangeEvalStack } from '../lib/fair-eval-stack';

const app = new App();
const env = { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? 'us-west-2' };
const ctx = (key: string, placeholder: string): string => app.node.tryGetContext(key) ?? placeholder;

// Issue #5: infra/deploy.sh deploys FairExchangeArtifacts, uploads the files the main stack reads, then deploys
// FairExchange with the artifact locations as context. Placeholders keep `cdk synth` working in CI.
new ArtifactsStack(app, 'FairExchangeArtifacts', {
  synthesizer: new BootstraplessSynthesizer(),
  env,
  docsTtlDays: Number(ctx('standardsDocsTtlDays', '30')),
});
// The application stack uses CDK's standard synthesizer (spec 05): deploy.sh bootstraps the account if needed.
new FairExchangeStack(app, 'FairExchange', {
  env,
  standards: {
    artifactsBucketName: ctx('artifactsBucket', 'unset-artifacts-bucket'),
    artifactsKeyArn: ctx('artifactsKeyArn', 'arn:aws:kms:us-west-2:000000000000:key/unset'),
    contentHash: ctx('standardsDocsHash', 'unset'),
  },
});

// Issue #4 spike (deploy-agent-spike.sh passes the code location as context; placeholders keep `cdk synth` working)
new AgentArtifactsStack(app, 'FairExchangeAgentArtifacts', { synthesizer: new BootstraplessSynthesizer(), env });
new AgentSpikeStack(app, 'FairExchangeAgentSpike', {
  synthesizer: new BootstraplessSynthesizer(),
  env,
  codeBucketName: app.node.tryGetContext('agentCodeBucket') ?? 'unset-agent-code-bucket',
  codeKey: app.node.tryGetContext('agentCodeKey') ?? 'hello/unset.zip',
});

// Spec 28: records table -> S3 -> Glue/Athena. The records table and its stream come from the write-back work (spec 26);
// pass them with -c recordsTableName=... -c recordsTableStreamArn=... (placeholders keep `cdk synth` working).
const athenaSync = new AthenaSyncStack(app, 'FairExchangeAthenaSync', {
  synthesizer: new BootstraplessSynthesizer(),
  env,
  recordsTableName: app.node.tryGetContext('recordsTableName') ?? 'unset-records-table',
  recordsTableStreamArn: app.node.tryGetContext('recordsTableStreamArn')
    ?? `arn:aws:dynamodb:${env.region}:000000000000:table/unset-records-table/stream/2026-01-01T00:00:00.000`,
  recordsTableKeyArn: app.node.tryGetContext('recordsTableKeyArn'),
  codeBucketName: app.node.tryGetContext('syncCodeBucket') ?? 'unset-sync-code-bucket',
  codeKey: app.node.tryGetContext('syncCodeKey') ?? 'sync/unset.zip',
});

// Spec 29: the analytics route's fixed queries, as Athena named queries in the workgroup above.
const analyticsQueries = new AnalyticsQueriesStack(app, 'FairExchangeAnalyticsQueries', {
  synthesizer: new BootstraplessSynthesizer(),
  env,
});
analyticsQueries.addDependency(athenaSync);

// Spec 36: the eval stack — the six code-based evaluator Lambdas plus the disposable eval data
// (records table + evidence bucket, kept apart from demo/reviewer data). The eval deploy step
// uploads the evaluator zip (eval/src/fx_evals + agent/src/fex) and passes it as context;
// placeholders keep `cdk synth` working in CI. The judge model defaults to the app's large model.
new FairExchangeEvalStack(app, 'FairExchangeEval', {
  env,
  codeBucketName: ctx('evalCodeBucket', 'unset-eval-code-bucket'),
  codeKey: ctx('evalCodeKey', 'eval/unset.zip'),
  codeKeyArn: app.node.tryGetContext('evalCodeKeyArn'),
  judgeModelId: ctx('evalJudgeModelId', 'us.amazon.nova-pro-v1:0'),
});
