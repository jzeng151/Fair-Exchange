#!/usr/bin/env bash
# Run the real agent and the real chat API together on this machine and drive one full conversation (#101).
#   bash scripts/e2e/run_local.sh            # deterministic demo model: no AWS, no cost
#   FEX_DEMO_MODELS=0 bash scripts/e2e/run_local.sh   # real Claude via Bedrock (needs AWS credentials; costs cents)
# Leaves both servers stopped. Records are written to $FEX_LOCAL_RECORDS_DIR (default: a temp folder).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
export FEX_DEMO_MODELS="${FEX_DEMO_MODELS:-1}"
export FEX_LOCAL_RECORDS_DIR="${FEX_LOCAL_RECORDS_DIR:-$(mktemp -d)}"
export FEX_AGENT_PORT="${FEX_AGENT_PORT:-8080}" FEX_API_PORT="${FEX_API_PORT:-3000}"
export FEX_AGENT_URL="http://127.0.0.1:${FEX_AGENT_PORT}"
[[ "$FEX_DEMO_MODELS" == "1" ]] || unset FEX_DEMO_MODELS
logs="$(mktemp -d)"

# Never talk to a server left over from an earlier run: it may be running old code.
for port in "$FEX_AGENT_PORT" "$FEX_API_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Stop that process first (lsof -nP -iTCP:$port -sTCP:LISTEN)." >&2
    exit 1
  fi
done
# uv and npx start the servers as child processes, so stop whatever listens on our ports.
cleanup() {
  for port in "$FEX_AGENT_PORT" "$FEX_API_PORT"; do
    lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
  done
}
trap cleanup EXIT

(cd "$root/agent" && uv sync --locked -q && uv run --no-sync python scripts/serve_local.py) >"$logs/agent.log" 2>&1 &
(cd "$root/api" && npm ci --silent && npx --yes tsx@4.19.2 src/local/main.ts) >"$logs/api.log" 2>&1 &

wait_for() { for _ in $(seq 1 120); do curl -s -o /dev/null "$1" && return 0; sleep 1; done; echo "not ready: $1 (logs in $logs)"; exit 1; }
wait_for "http://127.0.0.1:${FEX_AGENT_PORT}/ping"
wait_for "http://127.0.0.1:${FEX_API_PORT}/conversations"
echo "agent :${FEX_AGENT_PORT} (demo model: ${FEX_DEMO_MODELS:-no, real Claude})  api :${FEX_API_PORT}  records: $FEX_LOCAL_RECORDS_DIR"

python3 "$root/scripts/e2e/local_conversation.py" --api "http://127.0.0.1:${FEX_API_PORT}" --records "$FEX_LOCAL_RECORDS_DIR"
