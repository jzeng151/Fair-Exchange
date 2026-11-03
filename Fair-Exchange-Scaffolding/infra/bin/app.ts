#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import { FairExchangeStack } from '../lib/fair-exchange-stack';

const app = new App();
new FairExchangeStack(app, 'FairExchange', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? 'us-west-2' },
});
