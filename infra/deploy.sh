#!/usr/bin/env bash
# Issue #5: one command that builds, provisions, loads data and publishes Fair Exchange, in dependency order.
#   EXPECTED_AWS_ACCOUNT=100300582834 AWS_REGION=us-west-2 bash infra/deploy.sh
# Optional: STANDARDS_DOCS_TTL_DAYS (default 30) - days before uploaded clause documents expire.
# Needs: AWS credentials that can create IAM roles, KMS keys, Bedrock Knowledge Bases and S3 Vectors;
# access to Amazon Titan Text Embeddings V2 in the region; uv; Node 22. Bootstraps CDK in the account if needed.
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

step "1/8 Checking CDK bootstrap"
# The application stack uses CDK's standard synthesizer (docs/specs/05-cdk-stack.md), which needs a bootstrapped
# account. The bootstrap version parameter is how the CDK CLI itself checks.
if aws ssm get-parameter --name /cdk-bootstrap/hnb659fds/version >/dev/null 2>&1; then
  echo "Bootstrapped."
else
  echo "Not bootstrapped: running cdk bootstrap (creates the CDKToolkit stack)."
  (cd "$infra" && npm ci --silent && npx cdk bootstrap "aws://$account/$AWS_REGION")
fi

step "2/8 Building the website"
(cd "$repo/web" && npm ci --silent && npm run build)

step "3/8 Building one standards document per clause"
hash="$(cd "$repo/data" && uv run --quiet python -m fx_data.standards_kb "$build/docs")"
echo "Clause documents hash: $hash"

step "4/8 Checking the infrastructure code"
(cd "$infra" && npm ci --silent && npx tsc --noEmit)

step "5/8 Artifacts stack (artifacts key and bucket)"
synth
deploy FairExchangeArtifacts
bucket="$(output FairExchangeArtifacts ArtifactsBucketName)"
key_arn="$(output FairExchangeArtifacts ArtifactsKeyArn)"
[[ -n "$bucket" && "$bucket" != None && "$key_arn" == arn:aws:kms:* ]] || { echo "Artifacts stack outputs missing" >&2; exit 1; }

step "6/8 Uploading clause documents to s3://$bucket/clauses/"
# Freshly built files: sync re-uploads every document (resetting its expiry) and restores any that expired
# before an ingestion can run. --delete removes clauses that no longer exist.
aws s3 sync --only-show-errors --delete "$build/docs/clauses/" "s3://$bucket/clauses/"

step "7/8 Main stack (website hosting, standards Knowledge Base; ingestion runs when the clauses change)"
# cdk deploy (not aws cloudformation deploy): it publishes the stack's CDK assets through the bootstrap roles
(cd "$infra" && CDK_DEFAULT_ACCOUNT="$account" CDK_DEFAULT_REGION="$AWS_REGION" npx cdk deploy FairExchange \
  --require-approval never --progress events -c standardsDocsTtlDays="$ttl_days" \
  -c artifactsBucket="$bucket" -c artifactsKeyArn="$key_arn" -c standardsDocsHash="$hash")

step "8/8 Publishing the website and running smoke tests"
bash "$infra/publish-web.sh"
kb_id="$(output FairExchange StandardsKnowledgeBaseId)"
(cd "$repo/agent" && FEX_STANDARDS_KB_ID="$kb_id" uv run --quiet pytest -q -p no:cacheprovider \
  ../eval/tests/test_standards_kb_smoke.py)

echo
echo "Deployed in $((SECONDS - start))s."
echo "Website: $(output FairExchange WebUrl)"
echo "Standards Knowledge Base: $kb_id (set FEX_STANDARDS_KB_ID on the agent runtime)"
