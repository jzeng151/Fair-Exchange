#!/usr/bin/env bash
# Remove everything deploy-agent-spike.sh created (the runtime, its role, the code bucket).
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
aws cloudformation delete-stack --stack-name FairExchangeAgentSpike
aws cloudformation wait stack-delete-complete --stack-name FairExchangeAgentSpike
bucket="$(aws cloudformation describe-stacks --stack-name FairExchangeAgentArtifacts \
  --query "Stacks[0].Outputs[?OutputKey=='AgentCodeBucket'].OutputValue" --output text 2>/dev/null || true)"
[[ -n "$bucket" && "$bucket" != "None" ]] && aws s3 rm --only-show-errors --recursive "s3://$bucket"
aws cloudformation delete-stack --stack-name FairExchangeAgentArtifacts
aws cloudformation wait stack-delete-complete --stack-name FairExchangeAgentArtifacts
echo "Agent spike removed. CloudWatch log groups under /aws/bedrock-agentcore/runtimes/ are not removed and never expire by default. Delete them by hand."
