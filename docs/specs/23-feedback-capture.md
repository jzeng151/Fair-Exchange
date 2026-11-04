# Spec: Feedback capture (#23)

Status: approved for build, 2026-11-04.

## Problem Statement

FTUSA wants to know whether the guidance helped. That is the mechanism behind the grant's producer-satisfaction target. The answer needs to be captured exactly and stored on the record, and a misclick needs to be fixable.

## Solution

After the producer agrees to storage, FEX asks whether the guidance was helpful with three buttons. The answer is stored on the record and can be changed until the conversation closes.

## User Stories

1. As a producer, I want to be asked whether the guidance helped after I agree to storage, so that FTUSA learns whether this is useful.
2. As a producer, I want three simple choices, so that answering is quick.
3. As a producer, I want to change my answer until the conversation closes, so that a misclick is fixable.
4. As a producer, I want to end without answering, so that feedback is optional.
5. As an FTUSA reviewer, I want the feedback on the record, so that I can see whether the guidance helped.

## Implementation Decisions

- **When it's asked.** Feedback is asked only in the `feedback` step, which follows granted consent ([#13 spec](13-conversation-steps.md)). A declined conversation is not asked, because declined records have no field for it.
- **Action.** `set_feedback` takes `yes`, `somewhat` or `no`, matching the existing record schema. It stays in `feedback`, and a new `set_feedback` replaces the answer while the conversation is open.
- **No answer.** `end` without an answer stores no feedback.
- **Saving.** Each `set_feedback` saves the record ([#26 spec](26-write-back.md)). Changing consent to `declined` clears feedback ([#19 spec](19-consent-and-decline.md)).

## Testing Decisions

Seam 1 (agent entrypoint), per the [specs README](README.md). Cases:
- feedback stored on the completed record;
- a changed answer replacing the earlier one;
- `end` without an answer leaving feedback empty;
- feedback never asked after a decline;
- changing consent to declined clearing feedback.

## Out of Scope

- Free-text feedback
- Reporting on feedback (analytics, later batch)
