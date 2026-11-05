#!/usr/bin/env bash
# Remove the sample UI stack deployed by deploy/deploy.sh.
#   EXPECTED_AWS_ACCOUNT=<account> bash ui/sada/deploy/destroy.sh
# Deletes the Lambda, its URL, role and log group. The Django secret key is scheduled for deletion by Secrets
# Manager (7-30 days). The code bucket (fair-exchange-sample-ui-code-<account>-<region>) is kept for redeploys;
# empty and delete it yourself if you no longer need it.
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT to the account ID}"
stack="${STACK_NAME:-FairExchangeSampleUi}"
account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$account" == "$EXPECTED_AWS_ACCOUNT" ]] || { echo "Account mismatch: expected $EXPECTED_AWS_ACCOUNT, got $account" >&2; exit 1; }

aws cloudformation delete-stack --stack-name "$stack"
aws cloudformation wait stack-delete-complete --stack-name "$stack"
echo "Deleted $stack. Kept the code bucket fair-exchange-sample-ui-code-${account}-${AWS_REGION}."
