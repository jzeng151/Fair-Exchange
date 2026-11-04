#!/usr/bin/env bash
# Deploy the eval harness end to end against the event AWS account (#36):
#
#   EXPECTED_AWS_ACCOUNT=123456789012 AWS_REGION=us-west-2 bash deploy-eval.sh
#
# Packages the evaluator Lambdas (fx_evals + fex + ARM64 Linux wheels), uploads the zip to the
# artifacts bucket under a content-hash key, deploys the FairExchangeEval stack, then smokes all
# six evaluators against two fixture conversations. Tear down with
# `npx cdk destroy FairExchangeEval && aws s3 rm s3://<artifacts>/eval/ --recursive`
# (spec 36: the eval stack is disposable and never mixes with demo or reviewer data).
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Export EXPECTED_AWS_ACCOUNT before deploying.}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
if [ "$ACCOUNT" != "$EXPECTED_AWS_ACCOUNT" ]; then
    echo "Refusing to deploy against account $ACCOUNT (expected $EXPECTED_AWS_ACCOUNT)." >&2
    exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

echo "1/4 Packaging the evaluators (ARM64 Linux wheels for Lambda)"
uv pip install -q --target "$build/pkg" \
    --python-platform aarch64-manylinux2014 --python-version 3.12 --only-binary=:all: \
    pydantic boto3
cp -R "$ROOT/eval/src/fx_evals" "$build/pkg/"
cp -R "$ROOT/agent/src/fex" "$build/pkg/"
(cd "$build/pkg" && zip -qr -X "$build/evaluators.zip" .)
key="eval/fx-evals-$(shasum -a 256 "$build/evaluators.zip" | cut -d' ' -f1 | cut -c1-12).zip"

echo "2/4 Uploading the zip to the artifacts bucket"
cd "$ROOT/infra"
npm ci --silent
npx tsc --noEmit
npx cdk deploy FairExchangeAgentArtifacts --require-approval never >/dev/null
bucket=$(aws cloudformation describe-stacks --stack-name FairExchangeAgentArtifacts \
    --query 'Stacks[0].Outputs[?OutputKey==`AgentCodeBucket`].OutputValue' --output text)
aws s3 cp "$build/evaluators.zip" "s3://$bucket/$key"

echo "3/4 Deploying the eval stack"
deploy_args=(-c "evalCodeBucket=$bucket" -c "evalCodeKey=$key")
if [ -n "${EVAL_JUDGE_MODEL_ID:-}" ]; then
    deploy_args+=(-c "evalJudgeModelId=$EVAL_JUDGE_MODEL_ID")
fi
npx cdk deploy FairExchangeEval "${deploy_args[@]}" --require-approval never \
    --capabilities CAPABILITY_IAM >/dev/null

output() {
    aws cloudformation describe-stacks --stack-name FairExchangeEval \
        --query "Stacks[0].Outputs[?OutputKey==\`$1\`].OutputValue" --output text
}
table=$(output RecordsTableName)
evidence=$(output EvidenceBucketName)

echo "4/4 Smoking the evaluators against fixture conversations"
function_args=()
for pair in \
    "tag_overlap TagOverlapEvaluatorArn" \
    "citation_validity CitationValidityEvaluatorArn" \
    "answer_completeness AnswerCompletenessEvaluatorArn" \
    "directive_language DirectiveLanguageEvaluatorArn" \
    "enablement_tone EnablementToneEvaluatorArn" \
    "scope_leak ScopeLeakEvaluatorArn"; do
    evaluator=${pair%% *}
    arn=$(output "${pair##* }")
    function_args+=("--function" "$evaluator=$arn")
done
"$ROOT/agent/.venv/bin/python" "$ROOT/scripts/e2e/eval_smoke.py" \
    --records-table "$table" --evidence-bucket "$evidence" "${function_args[@]}"
