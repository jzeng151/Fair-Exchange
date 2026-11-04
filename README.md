# Fair-Exchange

Fair Trade USA Producer Exchange Agent: an AWS Breaking Barriers hackathon MVP. A producer describes a challenge in their own language, the agent plays back its understanding, answers with cited climate data and peer examples, and saves a tagged, consented record for human review.

**FEX** is the agent: a computer assistant for producers. It shares what the data shows and what other groups have tried (with sources and Fair Trade standard clauses), and never tells a producer what to do.

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
| [`data/`](data/) | Python 3.12 | Loaders: APS/FPS standards → clause records, regional fact table, sample data |
| [`eval/`](eval/) | Python 3.12 | Labeled scenarios, negative scope tests, evaluation harness |
| [`api/`](api/) | TypeScript (Node 20) | Lambda handlers (chat, write-back, review, analytics) and the generated record types |
| [`web/`](web/) | Vue 3 + Vite (TypeScript) | Producer chat and Fair Trade USA review/dashboard |
| [`infra/`](infra/) | CDK v2 (TypeScript) | The whole stack, one-command deploy; sandbox website publishing |
| [`docs/`](docs/) | Markdown | `requirements/` (vision, technical), `adr/` (decisions), `handoff/` (contracts, deploy) |

## Ground rules (from the requirements)

- **Scope is enforced in the tools, not the prompt.** Tools read `producer_id` from `tool_context.invocation_state`, which the API sets from the producer's login. Never expose it as a parameter the model can set.
- **Consent first.** Nothing narrative is saved without a yes. A decline is recorded as a successful outcome, with no narrative.
- **Flag PII, never redact it.**
- **Every claim carries a citation** (source + standard clause), enforced by the Pydantic schema.
- **Enablement, not direction.** FEX shares information. It never tells producers what they should do.
- **Light on the earth.** Use the smallest model that does each job well, and nothing runs idle.

## Getting started

Prerequisites: Python 3.12 (via [uv](https://docs.astral.sh/uv/)), Node 20+, AWS CLI, AWS CDK v2, and AWS credentials for your sandbox.

```bash
cd agent && uv sync && uv run pytest        # agent + schema
cd data  && uv sync && uv run pytest        # standards, data loaders
cd web   && npm ci && npm run dev           # web app
cd infra && npm ci && npx cdk synth         # preview the stack; creates nothing
```

### Run the whole chain locally (no AWS)

```bash
bash scripts/e2e/run_local.sh
```

This starts the real agent (`agent/scripts/serve_local.py`, served the way AgentCore runs it) and the real chat API
route logic (`api/src/local/`), then holds one full Spanish conversation through the API: intake, playback,
cited answer, consent, feedback, closing. It saves the record to a local folder. By default a deterministic demo
model stands in for Claude (`FEX_DEMO_MODELS=1`: no AWS, no cost); `FEX_DEMO_MODELS=0` uses real Claude via
Bedrock (needs AWS credentials). CI runs the same check on every PR.

**See it in the browser (live mode, #116):**

```bash
bash scripts/e2e/run_local.sh --web
```

This runs the same checks, then keeps the chain running and opens the web app with a **⚡ Live FEX** tab at
http://localhost:5173/#/live. Pick a sample producer and talk to the real agent. Every reply, cited claim,
consent choice and saved record comes from the chat API. The tab appears only when `VITE_FEX_API_URL` is set
at build time, so the published site still shows only the scripted demo. Live mode identifies the producer with
the local server's `x-demo-producer-id` header (a local-only stand-in). How people sign in once deployed is not
decided yet ([#11 spec](docs/specs/11-identity.md)).

How to contribute: [CONTRIBUTING.md](CONTRIBUTING.md).

## Docs

- [Vision document](docs/requirements/vision.md): problem, users, MVP scope, success criteria
- [Technical environment](docs/requirements/technical-environment.md): required stack, permitted and prohibited libraries, security baseline
- [Architecture decisions](docs/adr/) and [handoff docs](docs/handoff/)

The original `.docx` files from Fair Trade USA are in [`docs/requirements/source/`](docs/requirements/source/). They are the source of truth if the Markdown copies ever disagree.
