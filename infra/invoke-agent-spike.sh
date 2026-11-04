#!/usr/bin/env bash
# Invoke the #4 spike runtime:  bash invoke-agent-spike.sh <producerId> "<prompt>"
# The producerId stands in for what the chat API (#25) will take from the signed-in identity (#11).
set -euo pipefail
export AWS_PAGER=""
export AWS_REGION="${AWS_REGION:-us-west-2}"
arn="${ARN:-$(aws cloudformation describe-stacks --stack-name FairExchangeAgentSpike \
  --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" --output text)}"
payload="$(python3 -c 'import json,sys; print(json.dumps({"producerId": sys.argv[1], "prompt": sys.argv[2]}))' "${1:-P-001}" "${2:-Whose record is this?}")"
session="spike-$(uuidgen | tr '[:upper:]' '[:lower:]')"   # AgentCore needs 33+ characters
out="$(mktemp)"
aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn "$arn" --runtime-session-id "$session" \
  --content-type application/json --cli-binary-format raw-in-base64-out --payload "$payload" "$out" >/dev/null
cat "$out"; echo
rm -f "$out"
