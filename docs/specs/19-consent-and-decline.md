# Spec: Consent and decline (#19)

Status: approved for build, 2026-11-04. Revised 2026-11-04 after review.

## Problem Statement

Producers own their data, and a decline is a successful outcome, not an error. If consent is read from free text, a reply like "sí, pero..." can be misread. If the first click is final, a misclick overrides the producer's real choice. FTUSA also needs to see the final consent and how the producer got there.

## Solution

Consent is a button choice between three values. The producer can change it until the conversation closes. Every distinct choice is logged with its time. A declined consent produces a declined record with no narrative content.

## User Stories

1. As a producer, I want buttons asking whether a summary may be stored and for which use (FTUSA internal only, or also shared outward), so that my consent is explicit.
2. As a producer, I want to say no and have that treated as a normal outcome, so that declining does not feel like an error.
3. As a producer, I want to change my consent answer until the conversation closes, so that a misclick does not override my choice.
4. As a producer, I want changing from yes to no to remove my narrative from the record, so that my final choice is respected.
5. As a producer, I want changing from no back to yes to rebuild the record from my conversation, so that a misclick does not lose my account.
6. As a producer, I want ending the conversation after I chose to keep my choice, so that "I'm done" is never read as "delete it".
7. As a producer, I want typed questions during the consent step answered without changing my choice, so that I can ask what an option means.
8. As an FTUSA reviewer, I want every consent choice logged with its time, so that I can see the final choice and how it was reached.
9. As an FTUSA reviewer, I want a declined conversation counted with no narrative stored in the record, so that declines are visible without storing what was said.

## Implementation Decisions

### Consent choices (shared contract owned here)

- **The action.** `set_consent` takes `scope`, one of three values that match the record schema's consent scopes:

| Value | Meaning |
|---|---|
| `internal` | Stored for FTUSA's own review and trends |
| `internal_and_outward` | May also be shared outward (e.g., aggregated for partners) |
| `declined` | No narrative stored in the record |

- **Valid in** `consent` and `feedback`:
  - **Granted** (`internal` or `internal_and_outward`) moves to `feedback`.
  - **`declined`** stays in `consent`, so it can still be changed.
  - **Changing to `declined` from `feedback`** returns to `consent` and clears any feedback.
- **Same choice again.** Choosing the same scope as the current one changes nothing and adds no history entry.
- **Typed text** never sets or changes consent ([#13 spec](13-conversation-steps.md)).
- **A reopened playback** clears consent, which is asked again after the new answer.
- **Closing.** `end` and automatic closing ([#13 spec](13-conversation-steps.md)) close the conversation, keeping the latest consent choice.

### Declined record

- **When:** the latest consent choice at close is `declined`.
- **What gets saved:** a `DeclinedRecord` (identifiers, status, times, consent, consent history). The schema already rejects narrative fields on declined records.
- **Switching while open:** changing from granted to declined replaces the completed record with a declined one. Changing back rebuilds the completed record from the conversation state ([#13 spec](13-conversation-steps.md)). How saves work is in the [#26 spec](26-write-back.md).

### Consent history

Each distinct `set_consent` choice is appended to the record's `consent_history` with its time (field defined in the [#26 spec](26-write-back.md)). The history records only the producer's own choices; the system never adds entries on the producer's behalf. `consent.recorded_at` is the time of the latest choice.

## Testing Decisions

Seam 1 (agent entrypoint), per the [specs README](README.md). Cases:
- each consent value producing the right record type;
- granted to declined to granted, ending with a completed record and three history entries in order;
- the same choice twice adding one entry;
- `end` after a granted choice keeping it;
- a declined record carrying no narrative field;
- a reopen clearing consent;
- typed text in `consent` leaving consent unchanged.

## Out of Scope

- What happens to stored conversation text in memory ([memory spec](memory.md))
- The "your record" view (#32, later batch)

## Further Notes

### Not decided (do not build or assume)

- What happens to stored conversation text and derived memories when a producer declines
- What outcome and record a conversation gets when it closes without any consent choice
- How the record shows consent while a reopened playback is waiting for a new choice
