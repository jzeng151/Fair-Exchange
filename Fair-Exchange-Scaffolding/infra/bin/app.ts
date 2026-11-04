#!/usr/bin/env node
import { App, BootstraplessSynthesizer } from 'aws-cdk-lib';
import { FairExchangeStack } from '../lib/fair-exchange-stack';

const app = new App();
new FairExchangeStack(app, 'FairExchange', {
  synthesizer: new BootstraplessSynthesizer(),
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? 'us-west-2' },
});
