#!/usr/bin/env bash
# Deploy the sample UI (ui/sada) to AWS: one Lambda behind a public function URL (deploy/template.yaml).
#   EXPECTED_AWS_ACCOUNT=<account> bash ui/sada/deploy/deploy.sh
# Optional:
#   AWS_REGION=us-west-2               region (default us-west-2)
#   STACK_NAME=FairExchangeSampleUi    stack name (default FairExchangeSampleUi)
#   CONNECT_FEX_API=1                  turn on Real API mode with the deployed FairExchange stack's ApiUrl and
#                                      demo passcode (read from its outputs). Or pass FEX_API_URL and
#                                      DEMO_PASSCODE_SECRET_ARN yourself.
#   DATA_SOURCE=live                   what new sessions answer from (default mock)
#   LOG_RETENTION_DAYS=30              log retention (default 30)
# Remove it with deploy/destroy.sh. Needs the AWS CLI, uv, zip and curl, and credentials for the account.
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT to the account ID to deploy to}"
stack="${STACK_NAME:-FairExchangeSampleUi}"
for tool in aws uv zip curl; do command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }; done
account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$account" == "$EXPECTED_AWS_ACCOUNT" ]] || { echo "Account mismatch: expected $EXPECTED_AWS_ACCOUNT, got $account" >&2; exit 1; }

app="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
code_bucket="fair-exchange-sample-ui-code-${account}-${AWS_REGION}"

echo "1/5 Packaging the app (Python 3.12, x86_64 Linux wheels)"
pkg="$build/pkg"
uv pip install -q --target "$pkg" --python-platform x86_64-manylinux2014 --python-version 3.12 \
  --only-binary=:all: -r "$app/requirements.txt" apig-wsgi==2.20.0
# Only the app code: never .env (secrets), .venv, staticfiles from local runs, or docs.
cp -R "$app/config" "$app/exchange" "$pkg/"
cp "$app/manage.py" "$app/lambda_handler.py" "$pkg/"
find "$pkg" -name "__pycache__" -type d -prune -exec rm -rf {} +
rm -rf "$pkg/bin"
# Collect static files into the package (WhiteNoise serves them; DEBUG off needs the manifest). The packaged
# dependencies are all pure Python, so any local Python 3.12 can run Django from the package directory.
(cd "$pkg" && DJANGO_DEBUG=0 PYTHONPATH="$pkg" uv run -q --no-project --python 3.12 \
  python manage.py collectstatic --noinput -v 0)
(cd "$pkg" && zip -qr -X "$build/app.zip" .)
size_mb=$(( $(du -sk "$pkg" | cut -f1) / 1024 ))
(( size_mb < 240 )) || { echo "Package is ${size_mb} MB unzipped; Lambda allows 250 MB" >&2; exit 1; }
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }  # Linux / macOS
key="sample-ui/app-$(sha256 "$build/app.zip" | cut -c1-12).zip"  # new key per build, so CloudFormation sees the change
echo "    ${size_mb} MB unzipped -> $key"

echo "2/5 Real API connection"
fex_api_url="${FEX_API_URL:-}"
passcode_arn="${DEMO_PASSCODE_SECRET_ARN:-}"
if [[ "${CONNECT_FEX_API:-0}" == "1" ]]; then
  output() { aws cloudformation describe-stacks --stack-name FairExchange \
               --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
  fex_api_url="$(output ApiUrl)"
  passcode_arn="$(output DemoPasscodeSecretArn)"
  [[ -n "$fex_api_url" && "$fex_api_url" != "None" ]] || { echo "The FairExchange stack has no ApiUrl output" >&2; exit 1; }
  [[ "$passcode_arn" != "None" ]] || passcode_arn=""
fi
if [[ -n "$fex_api_url" ]]; then
  echo "    Real API: $fex_api_url"
  echo "    WARNING: this UI has no sign-in. Anyone with its URL can talk to the agent as the demo producers,"
  echo "    using the passcode held by the Lambda, and each answer uses Bedrock. Share the URL accordingly."
else
  echo "    Off: answers come from the mock (set CONNECT_FEX_API=1 to connect the deployed agent)"
fi

echo "3/5 Code bucket ($code_bucket)"
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
aws s3 cp --only-show-errors "$build/app.zip" "s3://$code_bucket/$key"

echo "4/5 Deploying $stack"
aws cloudformation deploy --stack-name "$stack" --template-file "$app/deploy/template.yaml" \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset --parameter-overrides \
  CodeBucket="$code_bucket" CodeKey="$key" DataSource="${DATA_SOURCE:-mock}" \
  FexApiUrl="$fex_api_url" DemoPasscodeSecretArn="$passcode_arn" LogRetentionDays="${LOG_RETENTION_DAYS:-30}"
url="$(aws cloudformation describe-stacks --stack-name "$stack" \
  --query "Stacks[0].Outputs[?OutputKey=='SampleUiUrl'].OutputValue" --output text)"
url="${url%/}"

echo "5/5 Smoke test ($url)"
# A new function URL's permissions can take a few seconds to apply.
check() { curl -s -o /dev/null -w "%{http_code}" --max-time 60 "$url$1"; }
for _ in $(seq 1 12); do [[ "$(check /healthz)" == "200" ]] && break; sleep 5; done
fail=0
for path in /healthz / /static/img/ftc-seal.png; do
  code="$(check "$path")"; echo "    $path -> $code"; [[ "$code" == "200" ]] || fail=1
done
curl -s --max-time 60 "$url/" | grep -q "Pick a persona to chat" || { echo "    / is missing the picker" >&2; fail=1; }
if (( fail )); then
  logs="$(aws cloudformation describe-stacks --stack-name "$stack" \
    --query "Stacks[0].Outputs[?OutputKey=='LogGroupName'].OutputValue" --output text)"
  echo "Smoke test failed. Recent logs: aws logs tail $logs --since 15m" >&2
  exit 1
fi

echo
echo "Done: $url/"
