#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
    brew install uv
fi

if ! command -v python3.14 >/dev/null 2>&1; then
    brew install python@3.14
fi

uv venv --python 3.14 && source .venv/bin/activate
uv pip install -r requirements.txt

