#!/usr/bin/env bash
# Remove everything deploy-athena-sync.sh created (the sync stack and the code bucket).
# The records bucket, failed-batches bucket and Athena results bucket have RemovalPolicy.RETAIN, so
# CloudFormation keeps them: the record data outlives a teardown. Empty and delete them by hand if wanted.
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
account="$(aws sts get-caller-identity --query Account --output text)"
code_bucket="fair-exchange-sync-code-${account}-${AWS_REGION}"

aws cloudformation delete-stack --stack-name FairExchangeAthenaSync
aws cloudformation wait stack-delete-complete --stack-name FairExchangeAthenaSync

if aws s3api head-bucket --bucket "$code_bucket" 2>/dev/null; then
  aws s3 rm --only-show-errors --recursive "s3://$code_bucket"
  aws s3api delete-bucket --bucket "$code_bucket" --region "$AWS_REGION"
fi

cat <<'EOF'
Sync stack removed. Retained (delete by hand if wanted):
  - the records bucket (RecordsBucketName), its failed-batches bucket and the Athena results bucket;
  - the KMS key the stack created (RemovalPolicy.RETAIN).
EOF
