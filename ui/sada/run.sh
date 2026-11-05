#!/usr/bin/env bash
# Run the PoC UI locally: bash run.sh   (PORT=8099 bash run.sh to change the port)
# Behind a path proxy such as https://<host>/proxy/8000/, set the prefix so links include it:
#   PORT=8000 URL_PREFIX=/proxy/8000 bash run.sh   (or put URL_PREFIX in .env)
# Creates .venv and installs requirements.txt on first run. App settings and AWS credentials come from .env,
# which config/settings.py reads itself.
set -euo pipefail
cd "$(dirname "$0")"
port="${PORT:-8010}"

if [[ ! -x .venv/bin/python ]]; then
    if command -v uv >/dev/null 2>&1; then
        uv venv --python 3.12 .venv
    else
        python3 -m venv .venv
    fi
fi
if command -v uv >/dev/null 2>&1; then
    uv pip install --python .venv/bin/python -q -r requirements.txt
else
    .venv/bin/python -m pip install -q -r requirements.txt
fi

.venv/bin/python manage.py collectstatic --noinput -v 0
echo "Fair Trade Exchange UI: http://localhost:${port}/${URL_PREFIX:+ (links use the prefix ${URL_PREFIX})}"
exec .venv/bin/python manage.py runserver "0.0.0.0:${port}"
