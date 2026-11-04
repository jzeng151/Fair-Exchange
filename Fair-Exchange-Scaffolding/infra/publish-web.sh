#!/usr/bin/env bash
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
: "${EXPECTED_AWS_ACCOUNT:?Set EXPECTED_AWS_ACCOUNT}"
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$EXPECTED_AWS_ACCOUNT" ]] || { echo 'Wrong AWS account' >&2; exit 1; }
scaffold_root="$(cd "$(dirname "$0")/.." && pwd)"
stack_output() {
  aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name FairExchange \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}
web_bucket="$(stack_output WebBucketName)"
web_distribution="$(stack_output WebDistributionId)"
web_url="$(stack_output WebUrl)"
[[ -s "$scaffold_root/web/dist/index.html" ]] || { echo 'Build web before publishing' >&2; exit 1; }
aws s3 sync "$scaffold_root/web/dist/assets/" "s3://$web_bucket/assets/" --cache-control 'public,max-age=31536000,immutable'
aws s3 cp "$scaffold_root/web/dist/favicon.svg" "s3://$web_bucket/favicon.svg" --cache-control 'no-cache,max-age=0,must-revalidate'
aws s3 cp "$scaffold_root/web/dist/index.html" "s3://$web_bucket/index.html" --content-type text/html --cache-control 'no-cache,max-age=0,must-revalidate'
invalidation="$(aws cloudfront create-invalidation --distribution-id "$web_distribution" --paths '/*' --query Invalidation.Id --output text)"
aws cloudfront wait invalidation-completed --distribution-id "$web_distribution" --id "$invalidation"
smoke_file="$(mktemp)"
trap 'rm -f "$smoke_file"' EXIT
curl --fail --silent --show-error --retry 5 --retry-all-errors "$web_url/" -o "$smoke_file"
cmp "$scaffold_root/web/dist/index.html" "$smoke_file"
while IFS= read -r asset; do
  curl --fail --silent --show-error --retry 3 "$web_url/$asset" -o /dev/null
done < <(find "$scaffold_root/web/dist/assets" -type f | sed "s|$scaffold_root/web/dist/||")
echo "Deployed: $web_url"
