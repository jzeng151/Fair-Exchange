# Tutorial: use the platform end to end locally

Run FEX on your laptop, drive one full Spanish conversation from intake to a saved record, and read what
the platform actually wrote. The default path needs no AWS account and costs nothing — every command on
this page was verified against current `main` (2026-11-04).

You need: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node 20+, and a clone of this repository.

## 1. Run the whole chain

```bash
bash scripts/e2e/run_local.sh
```

One script starts three things:

- the **real agent** (`agent/scripts/serve_local.py`, served the way AgentCore Runtime runs it) on port 8080
- the **real chat API** (`api/src/local/main.ts`) on port 3000
- one scripted **Spanish conversation** through the API, from intake to a closed record

By default a deterministic demo model stands in for Claude (`FEX_DEMO_MODELS=1`): no AWS, no cost, same
replies every time. The script ends with `PASSED` and tells you where the record was saved (a temp
directory unless you set `FEX_LOCAL_RECORDS_DIR`).

**If a port is already taken** (the agent's default 8080 is a common casualty on laptops), the script
exits with the exact hint. Pick another:

```bash
FEX_AGENT_PORT=8091 bash scripts/e2e/run_local.sh
```

(`FEX_API_PORT` overrides the API's 3000 the same way.)

## 2. The conversation, step by step

The transcript prints as it runs. Here is what each beat is, using the run from 2026-11-04:

1. **Intake** — FEX greets and asks the open question, and it replies in the producer's language: write
   Spanish, get Spanish.
2. **Follow-ups** — it asks what happened, when it started, how severe it is, and what has been tried.
3. **Playback** — "Esto es lo que entendí…", the agent restates the challenge and asks if it got it right.
4. **Cited answer** — the heart of the platform. For a coffee-and-rainfall challenge in Cauca, Colombia
   the record carries two *insights* (`CHIRPS v2.0 rainfall`, `WRI Aqueduct 4.0`) and two *peer examples*
   (Higuera Producers' Group in Colombia, Jacaranda Growers' Collective in Peru). Every claim — insight
   or peer example — cites a source **and** a Fair Trade standard clause (here `APS 2.4.2.a`). FEX shares
   what the data shows and what other groups tried; it never says what to do.
5. **Consent** — before anything is saved, the producer is asked. Nothing narrative is stored without a
   yes; a decline is recorded as a successful outcome with no narrative.
6. **Feedback** — "Was this helpful?" then the conversation closes and the record is finalized.

## 3. Read the record

Open the JSON the script saved. The one from the verified run looks like this (abridged):

```json
{
  "record_id": "6e6029b3-3af4-4b95-a734-77fc514030bf",
  "version": 3,
  "status": "completed",
  "language": "es",
  "entity_type": "1st Grade",
  "summary_original": "La lluvia ha bajado mucho y la cosecha de café cayó este año. …",
  "tags": ["climate and weather"],
  "evidence": "full",
  "insights": [
    {
      "text": "Rainfall near the centre of Cauca, Colombia averaged 1,861 mm a year in 2024-2025, 11.5% below the 2014-2023 average of 2,103 mm.",
      "citation": {
        "source": "CHIRPS v2.0 rainfall (Climate Hazards Center, via SERVIR ClimateSERV)",
        "standard_clause": "APS 2.4.2.a",
        "strength": "nearest"
      }
    }
  ],
  "peer_examples": [
    {
      "text": "Higuera Producers' Group (1st Grade, Coffee, Colombia) funded a Premium project …",
      "citation": {
        "source": "Premium project, Higuera Producers' Group [PROJ-295DB6A0]",
        "standard_clause": "APS 2.4.2.a",
        "strength": "exact"
      }
    }
  ],
  "feedback": "yes",
  "review_status": "pending"
}
```

What to notice:

- `version: 3` — the record grew as the conversation went: consent saved v1, feedback updated v2, closing
  finalized v3. `consent_history` keeps the timeline.
- `summary_original` stays in Spanish; the English summary is filled in later by review (a demo run
  marks it explicitly).
- `tags`, `evidence`, `entity_type` are what Fair Trade staff will see on the review dashboard.
- `pii_flag` / `pii_matches` — the write-back path flags PII, never redacts it.
- `review_status: "pending"` — a human reviews every record after the conversation ends.

## 4. Real models (no demo)

```bash
FEX_DEMO_MODELS=0 bash scripts/e2e/run_local.sh
```

Same flow, real Claude via Bedrock — and two things demo mode shields you from, both verified on the
2026-11-04 event account:

**Model access.** The defaults are Claude Sonnet/Haiku. If your AWS account has no AWS Marketplace
subscription for those models, the first turn fails with `AccessDeniedException … aws-marketplace:` — the
IAM grants `bedrock` but not Marketplace. Point to a model your IAM covers instead:

```bash
FEX_SMALL_MODEL=us.amazon.nova-pro-v1:0 FEX_LARGE_MODEL=us.amazon.nova-pro-v1:0 \
FEX_DEMO_MODELS=0 bash scripts/e2e/run_local.sh
```

**Knowledge Bases.** The grounded answer is not in the model — it comes from the standards Knowledge Base.
The runtime needs its id:

```bash
export FEX_STANDARDS_KB_ID=<StandardsKnowledgeBaseId>   # output of the deployed stack
```

Without it the grounded-answer turn fails with `RuntimeError - The standards Knowledge Base is not
configured (FEX_STANDARDS_KB_ID)`: intake, follow-ups and playback still work (all of those were verified
on real models), but no claims stream until the stack is deployed. If you have no deployed stack, deploy
one — [the handoff deploy guide](handoff/02-deploy.md) takes a fresh account end to end — or stay in demo
mode, which runs the identical conversation over sample knowledge with zero AWS.

The eval stack is the real-AWS path that works standalone: `infra/deploy-eval.sh` stands up its own CDK
stack (Bedrock judge, six evaluators) and `eval_smoke.py` runs two records through it — no sandbox stack
required.

## 5. Run the quality checks yourself

The labeled evaluation suite runs offline, no AWS:

```bash
cd agent && uv run --no-sync pytest ../eval/tests
```

That is the same gate CI runs on every PR. The deployed eval harness (CDK stack, Bedrock judge,
six evaluators) is specified in `docs/specs/36-eval-harness.md` and deployed with `infra/deploy-eval.sh`.

## Where to go next

- `bash scripts/e2e/run_local.sh --web` — the same chain, kept running, with a live chat tab in the
  browser (see [README](../README.md)).
- [CONTRIBUTING.md](../CONTRIBUTING.md) — how we work: docs ride the PR they describe.
- [docs/handoff/](handoff/README.md) — deploy contracts and interfaces.
- [docs/specs/](specs/) — what each feature is specified to do.
