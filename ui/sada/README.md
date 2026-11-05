# Fair Trade Exchange — Producer Exchange PoC

A Django proof-of-concept chat UI for the Fair Trade USA Producer Exchange (SDD.md).
No sign-on. Pick a role (producer/consumer), a product, and a persona, then chat. The chat is
mocked today and shaped so the real Fair Exchange API (Strands on Amazon Bedrock AgentCore) can
replace one function later.

## Run locally
```
uv sync
cp .env.example .env   # add AWS creds only if USE_BEDROCK=1
uv run python manage.py collectstatic --noinput
uv run python manage.py runserver 0.0.0.0:8099
```
test
Or `bash run.sh`, which sets up `.venv` on first run and starts the server on http://localhost:8010.

**Mock or Real API:** the chat answers from a built-in mock, or from the real FEX agent through the Fair
Exchange chat API. See [docs/REAL-API.md](docs/REAL-API.md) to connect locally or to the deployed stack.

**Deploy to AWS:** `EXPECTED_AWS_ACCOUNT=<account> bash deploy/deploy.sh` (one Lambda with a public URL; see
[docs/REAL-API.md](docs/REAL-API.md#deploy-this-ui-to-aws)).

## Features
- Persona picker: one click per persona tile (role, product, location, language)
- Full-height chat with location map + (mocked) weather overlay
- Candidate questions per persona; follow-up suggestions after each answer
- Multilingual (en/es/fr/pt/sw/hi), voice input and read-aloud
- Guardrails: out-of-scope redirect, PII flagged (never redacted), suggestion tone, per-claim citations
- About, Docs, and an 8+2 minute Demo deck

All data is fictitious. `.env` holds secrets and is gitignored.
