#!/usr/bin/env bash
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT}"
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$EXPECTED_AWS_ACCOUNT" ]] || { echo 'Wrong AWS account' >&2; exit 1; }
cd "$(dirname "$0")"
web_bucket="$(aws cloudformation describe-stacks --stack-name FairExchange --query "Stacks[0].Outputs[?OutputKey=='WebBucketName'].OutputValue | [0]" --output text)"
web_distribution="$(aws cloudformation describe-stacks --stack-name FairExchange --query "Stacks[0].Outputs[?OutputKey=='WebDistributionId'].OutputValue | [0]" --output text)"
web_key="$(aws cloudformation describe-stack-resource --stack-name FairExchange --logical-resource-id WebKey7707EFB6 --query StackResourceDetail.PhysicalResourceId --output text)"
aws cloudformation deploy --stack-name FairExchangeGitHub --template-file github-oidc.json \
  --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset \
  --parameter-overrides "WebBucket=$web_bucket" "WebDistribution=$web_distribution" "WebKey=$web_key" "ValidationBranch=${VALIDATION_BRANCH:-}"
aws cloudformation describe-stacks --stack-name FairExchangeGitHub --query 'Stacks[0].Outputs' --output json
