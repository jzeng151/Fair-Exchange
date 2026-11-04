# Spec: PII flagging (#20)

Status: approved for build, 2026-11-04.

## Problem Statement

Producers sometimes name a person or share contact details. FTUSA policy is to flag that for human review and never redact it, because the producer's own words matter. A summary written by FEX may drop names, so checking only the summary misses them. A failed check must never be read as "no PII".

## Solution

Amazon Comprehend `DetectPiiEntities` scans the producer's own messages, in English and Spanish, each time the record is saved. It looks only for names, phone numbers, emails and addresses above a confidence threshold. Any hit sets the record's PII flag. A failed or unsupported check flags the record for review too. Nothing is redacted.

## User Stories

1. As an FTUSA reviewer, I want a record flagged when the producer named a person or shared contact details, so that I can decide what to do with it.
2. As an FTUSA reviewer, I want to see which kinds of PII were found, so that I know what to look for.
3. As an FTUSA reviewer, I want records whose check failed or ran in an unsupported language flagged too, so that an error never passes as clean.
4. As an FTUSA reviewer, I want to confirm or clear a flag, so that false alarms (e.g., "Cauca" read as an address) are resolved.
5. As a producer, I want my words kept as I said them, so that my voice is not altered.

## Implementation Decisions

- **Engine.** Amazon Comprehend `DetectPiiEntities`, called from Python in the agent process during record saves ([#26 spec](26-write-back.md)). The agent runtime role gets `comprehend:DetectPiiEntities`.
- **Input.** Every piece of text the producer typed: messages and `correct_playback` text. FEX's own summaries are not scanned.
- **Out-of-scope messages.** A message the out-of-scope detection function classifies as `out_of_scope` ([#21 spec](21-out-of-scope.md)) adds nothing to the record: no flag, no entity type and no match or context. Nothing from it is quoted in the record, so there is nothing for a reviewer to check, and #21 keeps the misdirected request out of the record.
- **Per-message status.** Each text has a scan status in the conversation state: `pending`, `done` or `failed`. At each save, every text that is `pending` or `failed` is scanned. A text marked `done` is never scanned again.
- **Language.** `en` and `es` are scanned. Any other conversation language sets the check result to `unsupported_language`.
- **Entity types.** `NAME`, `PHONE`, `EMAIL`, `ADDRESS` only, with a confidence threshold that is a configuration value, default 0.8.
- **Flag rules:**
  - Any qualifying hit sets `pii_flag` to true, adds the entity type to `pii_entity_types`, and adds the match to `pii_matches`.
  - `pii_check` is `failed` while any text is `failed`, `unsupported_language` for languages other than `en` and `es`, and `done` only when every text is `done`.
  - A Comprehend error sets `pii_flag` to true.
  - The flag stays set for the life of the conversation.
- **Record fields (completed records only; declined records have no narrative):**

| Field | Type | Meaning |
|---|---|---|
| `pii_flag` | bool (exists) | Needs PII review |
| `pii_entity_types` | list of `NAME`, `PHONE`, `EMAIL`, `ADDRESS` | Types found |
| `pii_matches` | list of `{entity_type, text, context, message_at}` | What matched, for the reviewer (decided 2026-11-04): the matched words and about 10 words either side from the producer's text. Removed if the record switches to declined. |
| `pii_check` | `done`, `failed`, `unsupported_language` | Overall check status, per the rules above |
| `pii_review` | `confirmed`, `cleared`, or null | Reviewer decision ([#27 spec](27-review-api.md)) |

- **Redaction.** Nothing is redacted anywhere: not in messages, memory or the record.
- **Where matches appear.** `pii_matches` is shown only through the reviewer API and view ([#27](27-review-api.md), [#31](31-reviewer-view.md)). Analytics never reads it.
- **Logs.** Logs record entity types and counts, never the matched text.

## Testing Decisions

- **Seam 1 (agent entrypoint) with Comprehend mocked (moto or a stub client):**
  - a name in a Spanish message flags the record with `NAME`;
  - a low-confidence `ADDRESS` below the threshold does not flag;
  - a Comprehend error flags with `failed`;
  - a French conversation flags with `unsupported_language`;
  - a failed text is rescanned at the next save, and `pii_check` stays `failed` until it succeeds;
  - `correct_playback` text is scanned;
  - mixed conversation: a grievance naming a worker (out of scope), then an in-scope challenge. The record's PII fields contain nothing from the grievance;
  - `pii_matches` holds the words and context, and is removed when consent changes to declined;
  - texts marked `done` are not scanned again;
  - no text is altered;
  - logs hold no matched text.

### Spike check (#4)

- Comprehend returns all four entity types for Spanish text.

## Out of Scope

- French PII detection, which comes with #24 through the Guardrail
- Detecting PII in FEX's own output
