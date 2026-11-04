# Spec: Write-back (#26)

Status: approved for build, 2026-11-04. Revised 2026-11-04 after review.

## Problem Statement

FTUSA needs exactly one trustworthy record per conversation. The record holds what the producer said, how FEX tagged it, what FEX told them, and what they consented to.

That record changes after it is first written. While the conversation is open, the producer can change consent or feedback, or reopen the playback and get a new answer. After it closes, a reviewer corrects tags and summaries. If the model decides when to save, a record can be skipped or duplicated. If saves can race, a change can be lost unseen.

## Solution

Code, never the model, saves the record at fixed points, in Python, next to the agent. The record ID is the conversation ID, so there is exactly one record per conversation. Every save is validated against the record models and written with a version and owner check.

The record carries its own history:
- every consent choice,
- every answer shown to the producer,
- the agent's original tags and summaries next to any reviewer corrections,
- whether the evidence was full or limited.

## User Stories

1. As an FTUSA reviewer, I want exactly one record per conversation, so that counts and joins are not inflated by duplicates.
2. As an FTUSA reviewer, I want every record marked source = "agent conversation", so that it is never confused with compliance reporting data.
3. As an FTUSA reviewer, I want the challenge tags from the 11-tag set on the record, so that conversations can be grouped by challenge.
4. As an FTUSA reviewer, I want the insights and peer examples FEX gave, each with its citation, so that I can check what the producer was told.
5. As an FTUSA reviewer, I want answers replaced after a reopened playback kept in the record, so that I see everything the producer was shown.
6. As an FTUSA reviewer, I want records with limited evidence marked, so that I can find and count gaps in data coverage.
7. As an FTUSA reviewer, I want the agent's original tags and summaries kept next to my corrections, so that tag accuracy can be measured against human review.
8. As an FTUSA reviewer, I want to review only records from closed conversations, so that a record does not change while I review it.
9. As a producer, I want my record never to contain another producer's data, so that my account stays mine.
10. As an FTUSA engineer, I want records validated by the same Pydantic models that generate the JSON Schema and TypeScript types, so that there is one schema source of truth.
11. As an FTUSA engineer, I want a save to fail loudly rather than silently overwrite, so that no change is lost.
12. As an FTUSA engineer, I want the agent runtime allowed to write only to the records table, so that an agent bug cannot touch other data.

## Implementation Decisions

### Save points (shared contract owned here)

- **Where it runs (decided 2026-11-04).** The record is built and saved in Python in the agent process, by code. The model has no save tool. This replaces the TypeScript write-back Lambda in the original architecture diagram and the scaffold's API README. The technical environment document permits Python Lambdas that wrap Python logic, and the record models are Python.
- **One record per conversation.** `record_id` is the conversation ID issued by the chat API ([#25 spec](25-chat-endpoint.md)).
- **When it's saved.** The record is created at the first of these, and updated at each one after:
  - `set_consent`
  - `set_feedback`
  - `end`
  - `auto_close`
- **Unchanged saves.** A save that would change nothing (e.g., a repeated identical action) writes nothing.
- **After a reopened playback.** The reopen and the new answer reach the record at the next save point.
- **Event.** Each save emits a `record_saved` event ([#13 spec](13-conversation-steps.md)).

### Building the record

- **Source.** The record is built from the conversation state ([#13 spec](13-conversation-steps.md)), not from the raw transcript.
- **Completed record:**
  - `summary_original`, `summary_english` and `tags` are the values generated at `confirm_playback`. Language rules are in the [#22 spec](22-spanish-exchange.md).
  - `language` and `entity_type` come from the conversation state, including entity type corrections.
  - `insights` and `peer_examples` are the current verified answer, and `evidence` is that answer's `full` or `limited` marker.
  - Earlier answers go to `earlier_answers`.
- **Declined record:** identifiers, status, times, consent and consent history only ([#19 spec](19-consent-and-decline.md)).
- **Switching type:** while the conversation is open, a record switches between completed and declined as consent changes. Switching back to completed rebuilds the narrative from the conversation state, including earlier answers.
- **PII flag:** `pii_flag` keeps its schema default until the PII spec (later batch) defines how it is set.

### Record schema changes (shared contract owned here)

Changes go in the Pydantic record models. JSON Schema and TypeScript types are regenerated, never hand-edited.

| Field | On | Type | Meaning |
|---|---|---|---|
| `updated_at` | both | datetime | Time of the latest save |
| `version` | both | integer, starts at 1 | Incremented on every save; used for conditional writes |
| `closed_at` | both | datetime or null | Set when the conversation closes. Records are reviewable only when set. |
| `consent_history` | both | list of `{scope, recorded_at}` | The producer's distinct consent choices, in order (`internal`, `internal_and_outward`, `declined`). Non-narrative, so allowed on declined records. |
| `evidence` | completed | `full` or `limited` | `limited` when the shown answer had no insights or no peer examples |
| `earlier_answers` | completed | list of `{given_at, reason, insights, peer_examples, evidence}` | Earlier answers, oldest first. `reason` is `reopened` (the full answer shown before a reopened playback) or `interrupted` (only the claims shown before a failed answer was retried). |
| `reviewer_tags` | completed | list of challenge tags, or null | Reviewer's corrected tags |
| `reviewer_summary_original` | completed | string or null | Reviewer's corrected summary in the producer's language |
| `reviewer_summary_english` | completed | string or null | Reviewer's corrected English summary |

- **Agent fields stay the agent's.** `tags`, `summary_original` and `summary_english` always hold the agent's output. Reviewer corrections never overwrite them.
- **Effective values** for queries are the reviewer's value if set, otherwise the agent's.
- **`consent.recorded_at`** is the time of the latest consent choice.

### Write rules (shared contract owned here)

- **Table:** one records table, partition key `record_id`, KMS encryption, Streams enabled ([#28 spec](28-athena-sync.md)).
- **Validation:** every save validates the record with the record models first. An invalid record is an error, not a partial write.
- **Conditional writes:**
  - A create is conditioned on the record not existing.
  - An update is conditioned on the stored `version` matching the one read and the stored `producer_id` matching the request's producer ID.
  - A failed condition is an error, logged and surfaced as an `error` event. It is not retried: the chat API's turn lock already serializes saves for a conversation, so a conflict means a bug.
- **Permissions:** the agent runtime role may read and write only this table.
- **Reviewer writes** (later spec) follow the same rules. They may change only the `reviewer_*` and review fields, and only on records with `closed_at` set.

## Testing Decisions

- **Seam 1 (agent entrypoint),** per the [specs README](README.md), with the record store on moto DynamoDB so conditional writes behave as in AWS. Cases:
  - one record per conversation across repeated saves;
  - a stale version or a different producer ID rejected;
  - completed to declined to completed switching, keeping earlier answers;
  - narrative fields absent on declined records;
  - `evidence: "limited"` on a limited-evidence conversation;
  - summaries and tags unchanged by later saves until a re-confirm;
  - claims shown before a failed answer kept in `earlier_answers` with reason `interrupted`;
  - `closed_at` set on `end` and on `auto_close`.
- **Schema tests:** extend the existing record schema, schema parity and generated-types tests for the new fields.

## Out of Scope

- Sync to S3 and Athena ([#28 spec](28-athena-sync.md))
- The review view and API (later batch), beyond the write rules above
- PII detection (later batch)

## Further Notes

### Not decided (do not build or assume)

- How long records are kept
- The record for a conversation that closes without any consent choice ([#13 spec](13-conversation-steps.md))
- How the record shows consent while a reopened playback waits for a new choice ([#19 spec](19-consent-and-decline.md))

### Decisions made while writing this spec

- Records are reviewable only after the conversation closes, so producer changes and reviewer corrections never race on one record.
- A version-and-owner-conditioned write was chosen over a separate idempotency table, because the conversation ID as `record_id` already prevents duplicates.
