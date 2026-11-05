#!/usr/bin/env bash
# Issue #5: one command that builds, provisions, loads data and publishes Fair Exchange, in dependency order.
#   EXPECTED_AWS_ACCOUNT=100300582834 AWS_REGION=us-west-2 bash infra/deploy.sh
# Required (no defaults; the specs leave them to whoever deploys):
#   FEX_MAX_LIFETIME_MINUTES - maximum conversation lifetime (#25); must be shorter than memory's 7-day event expiry
#   LOG_RETENTION_DAYS       - retention of the agent runtime's log group (spec 05), a CloudWatch Logs value
# Optional: STANDARDS_DOCS_TTL_DAYS (default 30) - days before uploaded clause documents expire.
# Needs: AWS credentials that can create IAM roles, KMS keys, Bedrock Knowledge Bases and S3 Vectors;
# access to Amazon Titan Text Embeddings V2 in the region; uv; Node 22. Bootstraps CDK in the account if needed.
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT to your sandbox account ID}"
: "${FEX_MAX_LIFETIME_MINUTES:?Set FEX_MAX_LIFETIME_MINUTES (maximum conversation lifetime, minutes; no default)}"
: "${LOG_RETENTION_DAYS:?Set LOG_RETENTION_DAYS (agent runtime log retention, days; no default)}"
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

step "1/10 Checking CDK bootstrap and Transaction Search"
# The application stack uses CDK's standard synthesizer (docs/specs/05-cdk-stack.md), which needs a bootstrapped
# account. The bootstrap version parameter is how the CDK CLI itself checks.
if aws ssm get-parameter --name /cdk-bootstrap/hnb659fds/version >/dev/null 2>&1; then
  echo "Bootstrapped."
else
  echo "Not bootstrapped: running cdk bootstrap (creates the CDKToolkit stack)."
  (cd "$infra" && npm ci --silent && npx cdk bootstrap "aws://$account/$AWS_REGION")
fi
# AgentCore traces need CloudWatch Transaction Search, set once per account and region (ADR 0002).
destination="$(aws xray get-trace-segment-destination --query Destination --output text 2>/dev/null || true)"
if [[ "$destination" != CloudWatchLogs ]]; then
  echo "CloudWatch Transaction Search is off (trace destination: ${destination:-unknown}). Turn it on first;" >&2
  echo "see docs/adr/0002-agentcore-runtime-spike.md (Logs resource policy, then update-trace-segment-destination)." >&2
  exit 1
fi
echo "Transaction Search: on."

step "2/10 Installing the chat API's dependencies (bundled into its Lambdas by the stack)"
(cd "$repo/api" && npm ci --silent)

step "3/10 Building one standards document per clause"
hash="$(cd "$repo/data" && uv run --quiet python -m fx_data.standards_kb "$build/docs")"
echo "Clause documents hash: $hash"

step "4/10 Checking the infrastructure code"
(cd "$infra" && npm ci --silent && npx tsc --noEmit)

step "5/10 Artifacts stack (artifacts key and bucket)"
synth
deploy FairExchangeArtifacts
bucket="$(output FairExchangeArtifacts ArtifactsBucketName)"
key_arn="$(output FairExchangeArtifacts ArtifactsKeyArn)"
[[ -n "$bucket" && "$bucket" != None && "$key_arn" == arn:aws:kms:* ]] || { echo "Artifacts stack outputs missing" >&2; exit 1; }

step "6/10 Uploading clause documents to s3://$bucket/clauses/"
# Freshly built files: sync re-uploads every document (resetting its expiry) and restores any that expired
# before an ingestion can run. --delete removes clauses that no longer exist.
aws s3 sync --only-show-errors --delete "$build/docs/clauses/" "s3://$bucket/clauses/"

step "7/10 Packaging the agent (ARM64 Linux wheels, ADR 0002) and uploading it"
# The agent and data packages are built as wheels; their dependencies come from agent/uv.lock (minus the
# OpenTelemetry pins, which aws-opentelemetry-distro sets for the traces).
(cd "$repo/agent" && uv export --frozen --no-dev --no-hashes --no-emit-project --no-emit-package fx-data -q) \
  | grep -v -E '^opentelemetry-' > "$build/agent-requirements.txt"
uv build -q --wheel --out-dir "$build/dist" "$repo/data"
uv build -q --wheel --out-dir "$build/dist" "$repo/agent"
uv pip install -q --target "$build/agent" --python-platform aarch64-manylinux2014 --python-version 3.12 \
  --only-binary=:all: -r "$build/agent-requirements.txt" "$build"/dist/fx_data-*.whl "$build"/dist/fex_agent-*.whl \
  aws-opentelemetry-distro==0.22.0
cp "$repo/agent/runtime/fex/main.py" "$build/agent/main.py"
(cd "$build/agent" && find . -name '__pycache__' -prune -exec rm -rf {} + && zip -qr -X "$build/agent.zip" .)
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }  # Linux / macOS
agent_key="agent/fex-$(sha256 "$build/agent.zip" | cut -c1-12).zip"  # new key per build, so CloudFormation sees a change
aws s3 cp --only-show-errors "$build/agent.zip" "s3://$bucket/$agent_key"
echo "Agent code: s3://$bucket/$agent_key ($(du -h "$build/agent.zip" | cut -f1))"

step "8/10 Main stack (website hosting, standards Knowledge Base, data bucket, agent runtime, chat API)"
# Migration for stacks deployed before the data source used RETAIN: switch the existing data source first.
# A change that replaces the vector store also replaces the data source, and the old one is deleted after the
# Knowledge Base role's vector permission has moved to the new index. With DELETE, that cleanup fails and leaves
# the old data source and Knowledge Base behind. Deleting the old index removes the vectors anyway.
old_kb="$(output FairExchange StandardsKnowledgeBaseId 2>/dev/null || true)"
if [[ -n "$old_kb" && "$old_kb" != None ]]; then
  for ds in $(aws bedrock-agent list-data-sources --knowledge-base-id "$old_kb" --query 'dataSourceSummaries[].dataSourceId' --output text); do
    aws bedrock-agent get-data-source --knowledge-base-id "$old_kb" --data-source-id "$ds" --query dataSource > "$build/ds.json"
    if [[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("dataDeletionPolicy"))' "$build/ds.json")" == DELETE ]]; then
      echo "Setting data source $ds of $old_kb to RETAIN before the stack update"
      python3 - "$build/ds.json" > "$build/ds-update.json" <<'PY'
import json, sys
ds = json.load(open(sys.argv[1]))
update = {k: ds[k] for k in ("knowledgeBaseId", "dataSourceId", "name", "dataSourceConfiguration") if k in ds}
update.update({k: ds[k] for k in ("description", "vectorIngestionConfiguration", "serverSideEncryptionConfiguration") if ds.get(k)})
update["dataDeletionPolicy"] = "RETAIN"
print(json.dumps(update))
PY
      aws bedrock-agent update-data-source --cli-input-json "file://$build/ds-update.json" --query dataSource.dataDeletionPolicy --output text
    fi
  done
fi
# Analytics (#29): when the Athena sync stack exists (deploy-athena-sync.sh), deploy its fixed named queries and
# pass both stacks' outputs, which adds GET /analytics behind the admin passcode. Without it, no analytics route.
analytics_ctx=()
sync_key="$(output FairExchangeAthenaSync SyncKeyArn 2>/dev/null || true)"
if [[ "$sync_key" == arn:aws:kms:* ]]; then
  deploy FairExchangeAnalyticsQueries
  analytics_ctx=(-c analyticsQueryIds="$(output FairExchangeAnalyticsQueries AnalyticsNamedQueryIds)"
    -c analyticsWorkGroup="$(output FairExchangeAthenaSync AthenaWorkGroup)"
    -c analyticsRecordsBucket="$(output FairExchangeAthenaSync RecordsBucketName)"
    -c analyticsResultsBucket="$(output FairExchangeAthenaSync AthenaResultsBucketName)"
    -c analyticsKeyArn="$sync_key")
  echo "Analytics route: on (Athena workgroup $(output FairExchangeAthenaSync AthenaWorkGroup))"
else
  echo "Analytics route: off (deploy the Athena sync with infra/deploy-athena-sync.sh, then re-run)"
fi
# cdk deploy (not aws cloudformation deploy): it publishes the stack's CDK assets through the bootstrap roles
(cd "$infra" && CDK_DEFAULT_ACCOUNT="$account" CDK_DEFAULT_REGION="$AWS_REGION" npx cdk deploy FairExchange \
  --require-approval never --progress events -c standardsDocsTtlDays="$ttl_days" \
  -c artifactsBucket="$bucket" -c artifactsKeyArn="$key_arn" -c standardsDocsHash="$hash" \
  -c agentCodeKey="$agent_key" -c maxLifetimeMinutes="$FEX_MAX_LIFETIME_MINUTES" -c logRetentionDays="$LOG_RETENTION_DAYS" \
  -c version="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || echo unknown)" ${analytics_ctx[@]+"${analytics_ctx[@]}"})

step "9/10 Uploading the producer data to the data bucket (#7, #14; Glue tables over it for Athena)"
# Only allowlisted data: profiles, Premium projects, survey summary facts, certification scope, the peer catalog
data_bucket="$(output FairExchange DataBucketName)"
(cd "$repo/data" && uv run --quiet python -m fx_data.export "$build/data")
aws s3 sync --only-show-errors --delete "$build/data/" "s3://$data_bucket/"

step "10/10 Building and publishing the website (live mode uses the chat API), then smoke tests"
api_url="$(output FairExchange ApiUrl)"
(cd "$repo/web" && npm ci --silent && VITE_FEX_API_URL="$api_url" npm run build)
bash "$infra/publish-web.sh"
curl --fail --silent --show-error --retry 5 --retry-all-errors "${api_url%/}/health"; echo
kb_id="$(output FairExchange StandardsKnowledgeBaseId)"
(cd "$repo/agent" && FEX_STANDARDS_KB_ID="$kb_id" uv run --quiet pytest -q -p no:cacheprovider \
  ../eval/tests/test_standards_kb_smoke.py)

echo
echo "Deployed in $((SECONDS - start))s."
echo "Website: $(output FairExchange WebUrl)"
echo "Standards Knowledge Base: $kb_id"
echo "Chat API: $api_url"
echo "Demo passcode (sign-in stand-in, docs/specs/11-identity.md):"
echo "  aws secretsmanager get-secret-value --secret-id $(output FairExchange DemoPasscodeSecretArn) --query SecretString --output text"
admin_secret="$(output FairExchange AdminPasscodeSecretArn)"
if [[ "$admin_secret" == arn:* ]]; then
  echo "Admin passcode (analytics):"
  echo "  aws secretsmanager get-secret-value --secret-id $admin_secret --query SecretString --output text"
fi
