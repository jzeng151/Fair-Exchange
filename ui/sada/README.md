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

## Features
- Persona picker: role -> product -> up to 3 personas from the vision doc regions
- Full-height chat with location map + (mocked) weather overlay
- Candidate questions per persona; follow-up suggestions after each answer
- Multilingual (en/es/fr/pt/sw/hi), voice input and read-aloud
- Guardrails: out-of-scope redirect, PII flagged (never redacted), suggestion tone, per-claim citations
- About, Docs, and an 8+2 minute Demo deck

All data is fictitious. `.env` holds secrets and is gitignored.
