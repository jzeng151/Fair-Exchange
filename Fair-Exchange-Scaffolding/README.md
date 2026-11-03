# Fair Exchange (scaffolding)

Fair Trade USA's Producer Exchange Agent, built for AWS Breaking Barriers 2026.

**FEX** is a computer assistant for producers. A producer describes a challenge in their own language. FEX plays back what it understood, shares what the data shows and what other groups have tried (with sources and Fair Trade standard clauses), and, with consent, saves a tagged record that Fair Trade USA staff review.

> **Status:** scaffolding only. Folders, configuration and placeholder code with `TODO`s. No features are implemented yet. Each folder is filled in through the issues in the team backlog.

## Architecture

```
Producer (web)  ──▶  API Gateway + Lambda (TypeScript)  ──▶  FEX agent (Strands, Python)
  web/                api/                                     agent/  on Bedrock AgentCore Runtime
                                                                 │      + Bedrock Guardrails
                                                                 ├─ get_producer_record  ─▶ Athena / Glue (data/)
                                                                 ├─ get_regional_context ─▶ S3 regional table (data/)
                                                                 ├─ find_peer_examples   ─▶ Knowledge Base (Premium projects)
                                                                 └─ check_standards      ─▶ Knowledge Base (APS / FPS clauses)
On consent: write-back Lambda ─▶ Comprehend (flag PII, never redact) ─▶ DynamoDB record (pending review)
Fair Trade USA staff: dashboard + review (web/) ◀── review & analytics API (api/)
Everything deployed with one CDK command (infra/). Quality measured in eval/.
```

All model access goes through **Amazon Bedrock**. Use the `us.` inference profiles so processing stays in US regions.

## Folders

| Folder | Language | What goes here |
|---|---|---|
| [`agent/`](agent/) | Python 3.12 | Strands agent (FEX), tools, Pydantic schemas (the single schema source) |
| [`data/`](data/) | Python 3.12 | Loaders: sample data → S3/Athena, APS/FPS standards → clause records, regional fact table |
| [`eval/`](eval/) | Python 3.12 | Labeled scenarios, negative scope tests, evaluation harness |
| [`api/`](api/) | TypeScript (Node 20) | Lambda handlers: chat, write-back, review, analytics |
| [`web/`](web/) | Vue 3 + Vite (TypeScript) | Producer chat and Fair Trade USA review/dashboard |
| [`infra/`](infra/) | CDK v2 (TypeScript) | The whole stack, one-command deploy |
| [`docs/`](docs/) | Markdown | `requirements/` (vision, technical), `adr/` (decisions), `handoff/` (schemas, contracts, deploy) |

## Ground rules (from the requirements)

- **Scope is enforced in the tools, not the prompt.** Tools read `producer_id` from `tool_context.invocation_state`, which the API sets from the producer's login. Never expose it as a parameter the model can set.
- **Consent first.** Nothing narrative is saved without a yes. A decline is recorded as a successful outcome, with no narrative.
- **Flag PII, never redact it.**
- **Every claim carries a citation** (source + standard clause), enforced by the Pydantic schema.
- **Enablement, not direction.** FEX shares information. It never tells producers what they should do.
- **Light on the earth.** Use the smallest model that does each job well, and nothing runs idle.

## Getting started

Prerequisites: Python 3.12 (via [uv](https://docs.astral.sh/uv/)), Node 20+, AWS CLI, AWS CDK v2, Docker, and AWS credentials for your sandbox.

```bash
# agent
cd agent && uv sync && uv run pytest

# web
cd web && npm install && npm run dev

# infra (synth only; creates nothing)
cd infra && npm install && npx cdk synth
```

## Requirements

- [Vision document](docs/requirements/vision.md)
- [Technical environment](docs/requirements/technical-environment.md)
