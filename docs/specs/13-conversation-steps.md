# Spec: Conversation steps (#13)

Status: approved for build, 2026-11-04. Revised 2026-11-04 after review.

## Problem Statement

Today FEX is a single model call with no structure. Nothing makes it confirm what it heard before it fetches data. Nothing stops it skipping the consent question, and nothing stops it treating a vague reply as consent. If the conversation steps live only in the prompt, behavior varies from run to run and cannot be tested reliably.

## Solution

Code holds the conversation's current step and decides when it changes. The model writes the words; it never moves the conversation forward.

- **Buttons are actions.** Button choices arrive as structured actions, not chat text.
- **Tools are gated.** Data tools refuse to run outside the step where retrieval is allowed.
- **Only verified claims are shown.** The answer streams claim by claim, and each claim appears only after it passes the citation check.
- **Closing.** A conversation closes only when the producer ends it, it goes idle, or it reaches the maximum conversation lifetime. Until then, any button choice can be changed.

## User Stories

1. As a producer, I want FEX to open with an open question about what has been difficult, so that I describe the problem in my own terms.
2. As a producer, I want FEX to ask when the problem started, how severe it is and what I have tried, so that its answer fits my situation.
3. As a producer, I want FEX to confirm my location and entity type from my record rather than ask me to type them, so that I do not repeat what FTUSA knows.
4. As a producer, I want to correct my entity type, so that the record and the peer examples reflect my situation (e.g., a cooperative, not an individual farm).
5. As a producer, I want FEX to tell me if my location on file looks wrong rather than silently use a different one, so that I know FTUSA needs to update it.
6. As a producer, I want FEX to restate what it understood before it looks anything up, so that I can catch misunderstandings early.
7. As a producer, I want a "That's right" button and a "Correct this" option on the playback, so that my confirmation is unambiguous.
8. As a producer, I want to type a correction and see a revised playback, so that the corrected version is what gets recorded.
9. As a producer, I want FEX to fetch data only after I confirm the playback, so that it answers the problem I actually have.
10. As a producer, I want to reopen the playback after confirming it by mistake, so that a misclick does not lock in a wrong understanding.
11. As a producer, I want each insight and example to appear as soon as it is checked, so that I am not left waiting in silence.
12. As a producer, I want never to be shown a claim that FEX could not back up, so that I can trust what I see.
13. As a producer, I want FEX to say plainly when it has little or no evidence for my situation, so that I am not misled by a thin answer.
14. As a producer, I want to retry if FEX fails while answering, so that a technical error does not end my conversation.
15. As a producer, I want the answer framed as evidence and what others tried, not instructions, so that the decision stays mine.
16. As a producer, I want an option to end the conversation at any step that asks me to confirm, so that I can leave whenever I want but not by accident.
17. As a producer, I want any button choice to stay changeable until the conversation closes, so that misclicks are fixable.
18. As a producer, I want typed text in the consent or feedback step answered without changing my choices, so that a question like "what does 'shared outward' mean?" is safe to ask.
19. As an FTUSA reviewer, I want the record to reflect the confirmed playback, not the first draft, so that I review what the producer confirmed.
20. As an FTUSA engineer, I want step logic in code with tests, so that confirmation and consent cannot drift with prompt changes.
21. As an FTUSA engineer, I want data tools to refuse to run outside the retrieval step, so that a model mistake cannot retrieve data before confirmation.
22. As an FTUSA engineer, I want requests, actions and events defined as typed schemas generated for Python and TypeScript, so that the agent, API and web client cannot disagree on shapes.
23. As a tester, I want the scripted scenarios to run end to end without manual steps, so that the demo is repeatable.

## Implementation Decisions

### Steps (shared contract owned here)

The current step is kept in the conversation state (below), which is persisted in memory ([memory spec](memory.md)). Code changes it. The model never does.

| Step | What happens | How it advances | Data tools allowed |
|---|---|---|---|
| `intake` | Open question; follow-ups on timing, severity and what was tried; confirm location and entity type | The model signals through structured output that it has enough to play back | None |
| `playback` | FEX restates its understanding | `confirm_playback` moves to `respond`. `correct_playback`, or typed text, re-runs playback with the correction. | None |
| `respond` | Retrieval, then the claim-by-claim answer (below) | Moves to `consent` once the answer is complete, including a limited-evidence answer | Producer record, regional context, peer examples, standards |
| `consent` | Consent buttons ([#19 spec](19-consent-and-decline.md)) | `set_consent`. Granted moves to `feedback`. Declined stays in `consent`. | None |
| `feedback` | "Was this helpful?" buttons ([#23 spec](23-feedback-capture.md)) | `set_feedback` records the answer and stays in `feedback` | None |
| `closed` | No changes from the chat | Terminal | None |

- **Step gating.** Each data tool checks the current step before running. Outside `respond` it returns a refusal result, not data. The check is in code, like the producer ID scope rule.
- **Typed text outside intake and playback.** In `respond`, `consent` and `feedback`, typed text gets a short reply. Typed text never changes the step, the consent or the feedback, and it never triggers a data tool.
- **Profile at the start.** On `start`, code loads the producer's profile (location, entity type, crop) through a scoped lookup that uses the producer ID from the request context.
- **Entity type corrections.** If the producer corrects their entity type, the corrected value is used for the record and for peer-example matching. Entity type is not a scope field.
- **Location corrections.** Location is a scope field, so tools always use the profile location. If the producer says the location is wrong, FEX notes it in the conversation and summary and tells the producer it will use the location on file and that FTUSA can update it.
- **Summaries and tags.** These are generated once at `confirm_playback`, from the confirmed playback (small model, structured output). They are regenerated only after a later re-confirm.
- **Models.** Per ADR 0001, the small model handles intake questions, playback and tagging, and the large model writes the grounded answer. Model IDs are configuration values.
- **Prompt rules.** The existing system prompt rules stay in force: plain sentences, tools before answering, cite every fact, no directive language, hand the decision back.

### The answer: claim by claim (decided 2026-11-04)

- **Streaming.** Intake and playback text stream word by word as `text` events. In `respond`, the large model writes claims as JSON lines ([#18 spec](18-grounded-response.md)). Code checks each completed claim with the per-claim check ([#17 spec](17-standards-grounding.md)). A passing claim is sent at once as a `claim` event.
- **Failing claims** are never shown. Replacements and limits follow the [#18 spec](18-grounded-response.md). Claims that still fail are dropped and their reason codes logged.
- **No unchecked model text.** In `respond`, the only model-written text shown is checked claims. The opening line, the limited-evidence notice and the closing hand-back ("you and your committee know your situation best") are fixed text in the producer's language, written in code.
- **Limited evidence (decided 2026-11-04).** If the finished answer has no insights or no peer examples, FEX shows the fixed limited-evidence notice for what is missing (e.g., "I don't have rainfall or labor data for your region yet") and still moves to `consent`. The `answer` event and the record carry `evidence: "limited"` ([#26 spec](26-write-back.md)). Otherwise `evidence` is `"full"`.
- **Failures.** If the model call or a tool fails in `respond`, FEX sends an `error` event and stays in `respond`. The `retry_answer` action re-runs retrieval and the answer. Any claims already shown in the failed attempt first move to earlier answers with reason `interrupted`, so the record keeps everything the producer saw.

### Conversation state (shared contract owned here)

This is what the agent keeps per conversation, persisted through memory and rebuilt on every request:
- `step`
- `language`
- the profile loaded at `start`
- entity type and location notes from corrections
- the confirmed playback, with its summaries and tags
- the current verified answer and its `evidence`
- earlier answers
- consent history and current consent
- feedback
- the session evidence (sources and clause IDs returned by tools)
- the decision log entries and token usage ([#26 spec](26-write-back.md))
- PII check results ([#20 spec](20-pii-flagging.md))

The record is built from this state ([#26 spec](26-write-back.md)), not from the raw transcript.

### Agent runtime permissions (shared contract owned here)

The AgentCore runtime role gets only these permissions. Other specs refer here.
- DynamoDB read and write on the records table only ([#26 spec](26-write-back.md))
- The AgentCore Memory resource for this agent ([memory spec](memory.md))
- `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on the configured `us.` inference profiles
- `bedrock:ApplyGuardrail` on the FEX Guardrail ([#12 spec](12-guardrail.md))
- `bedrock:Retrieve` on the standards Knowledge Base ([#17 spec](17-standards-grounding.md))
- `comprehend:DetectPiiEntities` ([#20 spec](20-pii-flagging.md))
- S3 read on the producer and peer data objects ([#14 spec](14-producer-record-tool.md))
- `kms:Decrypt` on the stack key for those S3 reads
- Only in stacks deployed with `evalAccess=true`: `s3:PutObject` on the eval evidence bucket ([#34 spec](34-negative-scope-tests.md))
- Only in stacks deployed with `evalAccess=true`: `kms:GenerateDataKey` on the stack key for evidence writes. Grant `kms:Decrypt` as well if evidence uploads use multipart upload.
- The key policy permits these uses by the runtime role. Scope KMS access to the stack key and, where supported, S3 use for the relevant buckets.

### Actions (shared contract owned here)

Buttons send structured actions. Actions never carry a producer ID or conversation ID; those come from the request context.

| Action | Arguments | Valid in | Effect |
|---|---|---|---|
| `confirm_playback` | none | `playback` | Generates summaries and tags; moves to `respond` |
| `correct_playback` | `text`, 1 to 1,000 characters | `playback` | Re-runs playback with the correction |
| `reopen_playback` | none | `respond`, `consent`, `feedback` | Back to `playback`. The current answer moves to earlier answers (reason `reopened`). Consent and feedback are cleared and asked again. |
| `retry_answer` | none | `respond`, after an `error` | Moves any claims already shown to earlier answers (reason `interrupted`), then re-runs retrieval and the answer |
| `set_consent` | `scope`: `internal`, `internal_and_outward` or `declined` | `consent`, `feedback` | Defined in the [#19 spec](19-consent-and-decline.md) |
| `set_feedback` | `value`: `yes`, `somewhat` or `no` | `feedback` | Defined in the [#23 spec](23-feedback-capture.md) |
| `end` | none | every step except `closed` | Closes the conversation, keeping the latest consent and feedback, if any. The client confirms with the producer before sending it. It may be labeled "Stop" before consent and "End conversation" after. |

- **Repeated actions.** Repeating an action with the same arguments as the current state changes nothing and adds no history entry. That makes retries safe.
- **Invalid actions** in the current step return an `error` event with code `invalid_action` and change nothing.

### Closing rules (shared contract owned here)

- Only `end` and automatic closing close a conversation. Every other choice stays changeable while it is open.
- **Automatic closing.** The chat API's sweep ([#25 spec](25-chat-endpoint.md)) sends an `auto_close` request with a `reason`:
  - `inactivity`: idle longer than the inactivity period;
  - `max_lifetime`: open longer than the maximum conversation lifetime, however active it is.

  `auto_close` is valid in every open step and closes the conversation exactly as `end` does. The maximum lifetime stops an active conversation outliving its stored messages ([memory spec](memory.md)).
- Once `closed`, nothing changes from the chat.

### Requests, actions and events (shared contract owned here)

These are defined as Pydantic models in the agent package, the same way as the record schema. JSON Schema and TypeScript types are generated from them and never hand-edited.

**Request.** Every request carries `producerId` and `conversationId`, both set by the chat API, plus `kind`:

| Kind | Extra fields | Sent by |
|---|---|---|
| `start` | none | Chat API |
| `message` | `text`, 1 to 4,000 characters | Chat API |
| `action` | `action`: `{ name, args }` per the action table | Chat API |
| `resume` | none | Chat API |
| `auto_close` | `reason`: `inactivity` or `max_lifetime` | Sweep only |

**Events.** Every event has `type` and `seq` (an increasing integer within the turn):

| `type` | Fields |
|---|---|
| `text` | `text` (a chunk) |
| `claim` | `claim_id`, `section` (`insights` or `peer_examples`), `claim` (a `Claim` from the record schema) |
| `answer` | `insights`, `peer_examples` (final verified lists), `evidence` (`full` or `limited`) |
| `step` | `step`, `language` |
| `actions` | `allowed` (list of action names), `language` |
| `record_saved` | `status`, `consent_scope` (or null), `version` |
| `error` | `code` (`agent_failed`, `invalid_action`, `closed`), `message` |
| `done` | none |

**Resume response.** A `resume` request returns one object:
- `step`, `language`, `allowed` actions;
- the latest `answer` (or null);
- `history`, an ordered list of `{ role: "producer" | "fex", text, at }` and `{ role: "action", name, args, at }` entries.

## Testing Decisions

Seam 1 (agent entrypoint), per the [specs README](README.md). Cases:
- every step transition, and every invalid action rejected in every step with `invalid_action`;
- data tools refusing outside `respond`;
- typed text in `consent` or `feedback` changing nothing;
- a correction, as an action or as typed text in `playback`, re-running playback;
- a reopen clearing consent and feedback, moving the answer to earlier answers, and producing a new answer;
- claim events containing only claims that pass the check;
- a failing claim never emitted, and a passing rewrite emitted later;
- an answer with no verified insights producing the limited-evidence notice, `evidence: "limited"`, and the move to `consent`;
- a model failure after at least one `claim` event, followed by `retry_answer`, with the shown claims kept in earlier answers with reason `interrupted`;
- `end` from every step;
- `auto_close` with each reason from every step;
- repeated identical actions adding no history;
- the profile location used by tools even after the producer disputes it.

The generated JSON Schema and TypeScript types are checked the same way as the record schema's: regenerate and fail on drift.

Seam 3 covers one scripted conversation through all steps, plus one limited-evidence scenario (e.g., a Vietnamese processor, a country the regional table does not cover).

## Out of Scope

- What the data tools return and clause matching ([#14](14-producer-record-tool.md), [#15](15-regional-context-tool.md), [#16](16-peer-example-tool.md), [#17](17-standards-grounding.md), [#18](18-grounded-response.md))
- Memory storage details ([memory spec](memory.md))
- Button labels and layout (web UI, later batch)
- AgentCore Gateway (decided 2026-11-04: after the MVP). Tools stay in the agent process so the producer ID scope rule keeps working. The handoff notes list Gateway as the path for adding tools later, with that scope rule as the design constraint.

## Further Notes

### Not decided (do not build or assume)

- The inactivity period and the maximum conversation lifetime
- What outcome and record a conversation gets when it closes (by `end` or automatic closing) without any consent choice. This covers leaving before the consent question and leaving after only an out-of-scope request.
