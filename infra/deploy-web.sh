#!/usr/bin/env bash
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT to your sandbox account ID}"
actual_account="$(aws sts get-caller-identity --query Account --output text)"
if [[ "$actual_account" != "$EXPECTED_AWS_ACCOUNT" ]]; then
  echo "Account mismatch: expected $EXPECTED_AWS_ACCOUNT, got $actual_account" >&2
  exit 1
fi
scaffold_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$scaffold_root/web"
npm ci
npm run build
cd "$scaffold_root/infra"
npm ci
npx tsc --noEmit
CDK_DEFAULT_ACCOUNT="$actual_account" CDK_DEFAULT_REGION="$AWS_REGION" npx cdk synth --quiet
aws cloudformation deploy --region "$AWS_REGION" --stack-name FairExchange \
  --template-file cdk.out/FairExchange.template.json --no-fail-on-empty-changeset
bash "$scaffold_root/infra/publish-web.sh"
