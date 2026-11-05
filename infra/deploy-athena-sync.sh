#!/usr/bin/env bash
# Spec 28: build the sync Lambda zip, upload it, and deploy the Athena sync stack (records -> S3 -> Glue/Athena).
#   EXPECTED_AWS_ACCOUNT=100300582834 \
#   RECORDS_TABLE_NAME=<table> RECORDS_TABLE_STREAM_ARN=<arn> \
#   [RECORDS_TABLE_KEY_ARN=<kms-arn>] bash deploy-athena-sync.sh
# The records table and its stream come from the write-back work (spec 26). Remove everything with
# destroy-athena-sync.sh.
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT to your sandbox account ID}"
: "${RECORDS_TABLE_NAME:?Set RECORDS_TABLE_NAME to the records table (spec 26)}"
: "${RECORDS_TABLE_STREAM_ARN:?Set RECORDS_TABLE_STREAM_ARN to the DynamoDB stream ARN of the records table}"
account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$account" == "$EXPECTED_AWS_ACCOUNT" ]] || { echo "Account mismatch: expected $EXPECTED_AWS_ACCOUNT, got $account" >&2; exit 1; }

infra="$(cd "$(dirname "$0")" && pwd)"
sync_src="$infra/../sync"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

# The code bucket is created outside the stack: the stack imports it by name, so the zip must exist
# before the stack deploys. One plain bucket per account, reused across builds.
code_bucket="fair-exchange-sync-code-${account}-${AWS_REGION}"

echo "1/4 Packaging the sync Lambda (x86_64 Linux wheels)"
# The Lambda uses boto3, which the runtime already provides; package the source with its deps, Lambda arch.
# Build fex-sync's own wheel first: --only-binary forbids building any source, including this package, so it
# applies to the dependencies only.
uv build -q --wheel --out-dir "$build/dist" "$sync_src"
uv pip install -q --target "$build/pkg" --python-platform x86_64-manylinux2014 --python-version 3.12 \
  --only-binary=:all: "$build"/dist/fex_sync-*.whl
(cd "$build/pkg" && zip -qr -X "$build/sync.zip" .)
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }  # Linux / macOS
key="sync/sync-$(sha256 "$build/sync.zip" | cut -c1-12).zip"  # new key per build, so CloudFormation sees the change

echo "2/4 Code bucket ($code_bucket)"
if ! aws s3api head-bucket --bucket "$code_bucket" 2>/dev/null; then
  # us-east-1 rejects a LocationConstraint; every other region requires one.
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$code_bucket" --region "$AWS_REGION" >/dev/null
  else
    aws s3api create-bucket --bucket "$code_bucket" --region "$AWS_REGION" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  fi
  aws s3api put-public-access-block --bucket "$code_bucket" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-encryption --bucket "$code_bucket" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
fi
aws s3 cp --only-show-errors "$build/sync.zip" "s3://$code_bucket/$key"

echo "3/4 Synthesizing and deploying FairExchangeAthenaSync"
cd "$infra"
# The app also synthesizes FairExchange, whose chat API Lambdas are bundled from api/ (needs its dependencies)
(cd "$infra/../api" && npm ci --silent)
npm ci --silent
npx tsc --noEmit
ctx=(-c recordsTableName="$RECORDS_TABLE_NAME"
     -c recordsTableStreamArn="$RECORDS_TABLE_STREAM_ARN"
     -c syncCodeBucket="$code_bucket" -c syncCodeKey="$key")
[[ -n "${RECORDS_TABLE_KEY_ARN:-}" ]] && ctx+=(-c recordsTableKeyArn="$RECORDS_TABLE_KEY_ARN")
CDK_DEFAULT_ACCOUNT="$account" CDK_DEFAULT_REGION="$AWS_REGION" \
  npx cdk synth --quiet FairExchangeAthenaSync "${ctx[@]}" >/dev/null
aws cloudformation deploy --stack-name FairExchangeAthenaSync --capabilities CAPABILITY_IAM \
  --template-file cdk.out/FairExchangeAthenaSync.template.json --no-fail-on-empty-changeset

echo "4/4 Outputs"
aws cloudformation describe-stacks --stack-name FairExchangeAthenaSync \
  --query "Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}" --output table

echo
echo "Done. Backfill or repair the records with the resync command:"
echo "  RECORDS_TABLE=$RECORDS_TABLE_NAME SYNC_BUCKET=<RecordsBucketName above> uv run --project $sync_src python -m fex_sync.resync"
echo "Query from the fex Athena workgroup; the named queries are journey-3-... and athena-only-tag-counts."
