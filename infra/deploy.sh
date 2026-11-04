#!/usr/bin/env bash
# Issue #5: one command that builds, provisions, loads data and publishes Fair Exchange, in dependency order.
#   EXPECTED_AWS_ACCOUNT=100300582834 AWS_REGION=us-west-2 bash infra/deploy.sh
# Optional: STANDARDS_DOCS_TTL_DAYS (default 30) - days before uploaded clause documents expire.
# Needs: AWS credentials that can create IAM roles, KMS keys, Bedrock Knowledge Bases and S3 Vectors;
# access to Amazon Titan Text Embeddings V2 in the region; uv; Node 22.
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT to your sandbox account ID}"
ttl_days="${STANDARDS_DOCS_TTL_DAYS:-30}"

account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$account" == "$EXPECTED_AWS_ACCOUNT" ]] || { echo "Account mismatch: expected $EXPECTED_AWS_ACCOUNT, got $account" >&2; exit 1; }

infra="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$infra/.." && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
start=$SECONDS

step() { echo; echo "== $1 ($((SECONDS - start))s)"; }
output() {
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue | [0]" --output text
}
synth() {
  (cd "$infra" && CDK_DEFAULT_ACCOUNT="$account" CDK_DEFAULT_REGION="$AWS_REGION" \
    npx cdk synth --quiet -c standardsDocsTtlDays="$ttl_days" "$@" >/dev/null)
}
deploy() {  # stack name, extra args
  local stack="$1"; shift
  aws cloudformation deploy --stack-name "$stack" --template-file "$infra/cdk.out/$stack.template.json" \
    --no-fail-on-empty-changeset "$@"
}

step "1/7 Building the website"
(cd "$repo/web" && npm ci --silent && npm run build)

step "2/7 Building one standards document per clause"
hash="$(cd "$repo/data" && uv run --quiet python -m fx_data.standards_kb "$build/docs")"
echo "Clause documents hash: $hash"

step "3/7 Checking the infrastructure code"
(cd "$infra" && npm ci --silent && npx tsc --noEmit)

step "4/7 Artifacts stack (data key and artifacts bucket)"
synth
deploy FairExchangeArtifacts
bucket="$(output FairExchangeArtifacts ArtifactsBucketName)"
key_arn="$(output FairExchangeArtifacts DataKeyArn)"
[[ -n "$bucket" && "$bucket" != None && "$key_arn" == arn:aws:kms:* ]] || { echo "Artifacts stack outputs missing" >&2; exit 1; }

step "5/7 Uploading clause documents to s3://$bucket/clauses/"
# Freshly built files: sync re-uploads every document (resetting its expiry) and restores any that expired
# before an ingestion can run. --delete removes clauses that no longer exist.
aws s3 sync --only-show-errors --delete "$build/docs/clauses/" "s3://$bucket/clauses/"

step "6/7 Main stack (website hosting, standards Knowledge Base; ingestion runs when the clauses change)"
synth -c artifactsBucket="$bucket" -c dataKeyArn="$key_arn" -c standardsDocsHash="$hash"
deploy FairExchange --capabilities CAPABILITY_IAM

step "7/7 Publishing the website and running smoke tests"
bash "$infra/publish-web.sh"
kb_id="$(output FairExchange StandardsKnowledgeBaseId)"
(cd "$repo/agent" && FEX_STANDARDS_KB_ID="$kb_id" uv run --quiet pytest -q -p no:cacheprovider \
  ../eval/tests/test_standards_kb_smoke.py)

echo
echo "Deployed in $((SECONDS - start))s."
echo "Website: $(output FairExchange WebUrl)"
echo "Standards Knowledge Base: $kb_id (set FEX_STANDARDS_KB_ID on the agent runtime)"
