#!/usr/bin/env bash
# Issue #4 spike: build the agent code zip, upload it, deploy the AgentCore Runtime, and invoke it once.
#   EXPECTED_AWS_ACCOUNT=100300582834 bash deploy-agent-spike.sh
# Remove everything again with destroy-agent-spike.sh.
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT to your sandbox account ID}"
account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$account" == "$EXPECTED_AWS_ACCOUNT" ]] || { echo "Account mismatch: expected $EXPECTED_AWS_ACCOUNT, got $account" >&2; exit 1; }

infra="$(cd "$(dirname "$0")" && pwd)"
src="$infra/../agent/runtime/hello"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

echo "1/4 Packaging the agent (ARM64 Linux wheels for AgentCore)"
uv pip install -q --target "$build/pkg" --python-platform aarch64-manylinux2014 --python-version 3.12 \
  --only-binary=:all: -r "$src/requirements.txt"
cp "$src/main.py" "$build/pkg/"
(cd "$build/pkg" && zip -qr -X "$build/agent.zip" .)
key="hello/agent-$(shasum -a 256 "$build/agent.zip" | cut -c1-12).zip"   # new key per build, so CloudFormation sees the change

cd "$infra"
npm ci --silent
npx tsc --noEmit
synth() { CDK_DEFAULT_ACCOUNT="$account" CDK_DEFAULT_REGION="$AWS_REGION" npx cdk synth --quiet "$@" >/dev/null; }

echo "2/4 Code bucket"
synth
aws cloudformation deploy --stack-name FairExchangeAgentArtifacts \
  --template-file cdk.out/FairExchangeAgentArtifacts.template.json --no-fail-on-empty-changeset
bucket="$(aws cloudformation describe-stacks --stack-name FairExchangeAgentArtifacts \
  --query "Stacks[0].Outputs[?OutputKey=='AgentCodeBucket'].OutputValue" --output text)"
aws s3 cp --only-show-errors "$build/agent.zip" "s3://$bucket/$key"

echo "3/4 AgentCore Runtime (execution role + runtime)"
synth -c agentCodeBucket="$bucket" -c agentCodeKey="$key"
aws cloudformation deploy --stack-name FairExchangeAgentSpike --capabilities CAPABILITY_IAM \
  --template-file cdk.out/FairExchangeAgentSpike.template.json --no-fail-on-empty-changeset
arn="$(aws cloudformation describe-stacks --stack-name FairExchangeAgentSpike \
  --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" --output text)"
echo "Runtime: $arn"

echo "4/4 Invoking it once"
ARN="$arn" bash "$infra/invoke-agent-spike.sh" P-001 "Whose record is this?"
