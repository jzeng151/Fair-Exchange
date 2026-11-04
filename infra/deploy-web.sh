#!/usr/bin/env bash
# Kept for existing instructions. The full deploy (issue #5) is infra/deploy.sh: the FairExchange stack now
# also holds the standards Knowledge Base, which needs the artifacts stack and clause upload first.
set -euo pipefail
exec bash "$(cd "$(dirname "$0")" && pwd)/deploy.sh" "$@"
