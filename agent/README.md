# agent/

FEX, Fair Exchange's agent (Python 3.12). This holds the **conversation record schema** (issue #6) and the agent **tools**.

## Record schema

`src/fex/models.py` is the **single source of truth**. Two record types, chosen by `status`:

| | `CompletedRecord` | `DeclinedRecord` |
|---|---|---|
| When | The producer agreed to save | The producer declined |
| Consent scope | `internal` or `internal_and_outward` | `declined` |
| Content | Producer's words (+ English for non-English), 11-tag challenge tags, the insights and peer examples given (each with a required citation: source + APS/FPS clause + evidence strength), feedback, PII flag, review status | Identifiers, status and time only. Any narrative field is rejected |
| `source` | always `"agent conversation"` | always `"agent conversation"` |

Use `parse_record(data)` to validate stored or incoming data; it picks the type from `status`.

## Generated files (never edit by hand)

- `schema/conversation-record.schema.json` and `../api/src/types/conversation-record.ts`: the record (#6)
- `schema/conversation-contract.schema.json` and `../api/src/types/conversation-contract.ts`: requests, actions,
  events and the resume response between the chat API and the agent (#13)

After changing `models.py` or `conversation/contract.py`, regenerate (needs Node.js):

```bash
uv run python scripts/generate_types.py
```

`tests/test_generated_types.py` and `tests/test_generated_contract_types.py` fail if the models change without regenerating, or if a generated file is edited by hand.

## Tests

```bash
uv sync
uv run pytest
```

## Citation verifier (issue #17)

`src/fex/verifier.py` checks FEX's answer **after** it is written, deterministically (no model involved). Every insight and peer example must:

1. cite a **source a tool returned in this session**: tools add what they return to `SessionEvidence` (`record()` / `record_tool_result()`), so nothing can be invented;
2. cite a **clause that exists** in APS or FPS (via `fx_data.standards`, issue #9).

```python
from fex.verifier import SessionEvidence, generate_verified

evidence = SessionEvidence()
evidence.record_tool_result(peer_examples_from_tool)      # each tool, as it runs
result = generate_verified(write_answer, evidence, standards)
result.answer      # GroundedAnswer with verified claims only
result.attempts    # 1 = verified first time
result.removed     # problems behind any claim that was dropped
```

`write_answer(problems)` writes the answer; on a retry it receives the problems from the previous attempt so it can fix them. After `max_retries` (default 2), unverified claims are **removed and logged**, so they never reach the producer.

`agent/` depends on `data/` (`fx-data`) as a regular, non-editable install. After changing `data/`, run `uv sync --reinstall-package fx-data`.

## Conversation steps (issue #13)

`fex.conversation` runs one conversation per (producer ID, conversation ID), following
[`docs/specs/13-conversation-steps.md`](../docs/specs/13-conversation-steps.md). Code holds the step; the model only writes words.

```
intake → playback → respond → consent → feedback → closed
```

- **Entrypoint:** `ConversationEngine.handle(request)`, with `start`, `message`, `action`, `resume` and `auto_close`
  requests (`conversation/contract.py`). The AgentCore wrapper is `conversation/runtime.py`.
- **Models:** the small model (`FEX_SMALL_MODEL`) handles intake, playback, tagging and short replies, and is
  never offered data tools. The large model (`FEX_LARGE_MODEL`) retrieves in `respond` and writes claims as
  structured output.
- **Claim by claim:** each claim is checked by the citation verifier before it is sent as a `claim` event.
  Failures are rewritten up to the retry limit, then dropped and logged.
- **Fixed text:** in `respond`, the opening line, limited-evidence notice and hand-back come from `conversation/copy.py`.
- **State:** `ConversationState`, stored as JSON through a `StateStore` and rebuilt on every request.
  `InMemoryStateStore` is used until AgentCore Memory (`docs/specs/memory.md`) is built.
- **Tests:** `tests/test_conversation_steps.py` (seam 1: scripted Strands models in `tests/conversation_harness.py`,
  real tools and data, real verifier).

## Out-of-scope requests (issue #21)

Every typed message first goes through one detection function, `scope_check(text, step) -> ScopeVerdict`
(`fex/conversation/scope.py`), following [`docs/specs/21-out-of-scope.md`](../docs/specs/21-out-of-scope.md).
An out-of-scope message (another producer's data, certification or audit results, grievances) gets fixed
decline text in the producer's language plus an offer to return to the open question. No model is called, no
data tool runs, and the step stays the same. The exchange stays in the resume history but is never given to a
model, so it can't reach the playback, summaries or record. **How detection decides is "Not decided"**: the
default, `always_in_scope`, treats everything as in scope. Pass `scope_check=` to `ConversationEngine` to plug one in.
The check also covers text sent with `correct_playback`. A verdict can carry the message's `language`, so a
producer whose first message is out of scope still gets the decline in their own language (no model is called).

## Guardrail (issue #12)
Both models are `GuardedBedrockModel`s (`fex/guardrail.py`), following [`docs/specs/12-guardrail.md`](../docs/specs/12-guardrail.md).
The Bedrock Guardrail is attached from `FEX_GUARDRAIL_ID` and `FEX_GUARDRAIL_VERSION`, with the trace on and
input and output redaction explicitly off. Every policy is detect-only (CDK: `infra/lib/guardrail.ts`), so it
never blocks or changes a conversation. Each detected policy is logged as one `guardrail_finding` JSON line
(`conversation_id`, `source`, `policy`, `category`) at WARNING. It is never text, and never written to the record.
If either variable is unset, the models run without the Guardrail and a warning is logged.
Tests: `tests/test_guardrail.py`.
## Write-back (issue #26)

`fex.records` builds the record from the conversation state and saves it, following
[`docs/specs/26-write-back.md`](../docs/specs/26-write-back.md). Code saves; the model has no save tool.

- **Save points:** `set_consent`, `set_feedback`, `end` and `auto_close`. Each save emits `record_saved`. A save
  that would change nothing writes nothing. No record exists before the first consent choice.
- **One record per conversation:** `record_id` is the conversation ID. Completed and declined records switch as
  consent changes; earlier answers (`reopened`, `interrupted`) and the consent history are kept.
- **Write rules:** validated with the record models before writing. A create requires that the record doesn't
  exist. An update requires that the stored `version` is the one this conversation last saved and that the stored
  `producer_id` matches. A failed condition raises `RecordConflict` and becomes an `error` event, never retried.
- **Where:** `DynamoRecordStore` on the table named by `FEX_RECORDS_TABLE` (unset: records aren't saved).
  The table itself (KMS, Streams) and the runtime role's permissions are CDK work (#5, #28).
- **Tests:** `tests/test_write_back.py` runs the entrypoint against moto DynamoDB, so conditional writes behave as in AWS.

## Tools

Every tool is `@tool(context=True)` and learns who the producer is only through `fex.tools._scope.session_producer_id`, which reads `tool_context.invocation_state["producer_id"]`. No tool takes a producer, location or crop parameter; `tests/test_scope_guard.py` checks this for every tool in `ALL_TOOLS`. Contracts are in [`docs/handoff/tool-contracts.md`](../docs/handoff/tool-contracts.md).

Tool tests call each tool through Strands' own `stream()` (`tests/tool_harness.py`), so session-context injection is tested for real.
