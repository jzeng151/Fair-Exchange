# Spec: Reviewer view (#31)

Status: approved for build, 2026-11-04.

## Problem Statement

Journey 3 needs a reviewer to see a conversation become a reusable record, check it, correct it and approve it. Without a view, reviewers would read raw JSON, and the agent's original output and the reviewer's corrections would be hard to tell apart.

## Solution

A reviewer route in the existing Vue app, backed by the Review API ([#27 spec](27-review-api.md)). It has a list of records and a detail page. The detail page shows the agent's version next to the reviewer's, with controls to correct, decide on PII and approve.

## User Stories

1. As a reviewer, I want a list of records with their status, tags, language, PII flag and evidence marker, so that I can choose what to review.
2. As a reviewer, I want to filter the list by review status, PII flag and limited evidence, so that I can prioritize.
3. As a reviewer, I want to see the producer's summary in their language and in English side by side, so that I can check the translation.
4. As a reviewer, I want each insight and peer example with its source, clause and strength, so that I can check grounding.
5. As a reviewer, I want earlier answers and the consent history, so that I know what the producer saw and agreed to.
6. As a reviewer, I want the decision log, so that I can see the agent's reasoning (Journey 3).
7. As a reviewer, I want the PII flag highlighted with each match shown in its surrounding words, plus confirm and clear buttons, so that I can resolve it accurately.
8. As a reviewer, I want to edit tags from the 11-tag set and edit both summaries, with the agent's version still visible, so that I correct without losing the original.
9. As a reviewer, I want to approve with one button, so that the record is marked reviewed.
10. As a reviewer, I want a clear message and a reload option if the record changed under me, so that I do not overwrite someone else's work.

## Implementation Decisions

- **Placement.** Vue 3 with TypeScript, in the same app as the chat, under a reviewer route. It is shown only to users with the `reviewer` role, which the app learns from `GET /me` ([#11 spec](11-identity.md)). The API enforces the role either way.
- **Types.** Generated TypeScript record types, never hand-written.
- **List page.** Calls `GET /records` with the filter controls. Rows link to the detail page.
- **Detail page sections:**
  1. Header: status, language, entity type, closed time, evidence marker.
  2. Summaries, showing original and English and the agent versus reviewer values.
  3. Tags, showing agent versus reviewer.
  4. The current answer's claims with citations.
  5. Earlier answers.
  6. Consent history.
  7. PII.
  8. Decision log.
  9. Feedback.
- **Editing.** Reviewer edits send `PATCH` with the loaded `version`. Approve sends `POST .../approve`. On 409, the page shows "This record changed. Reload to see the latest." and keeps the unsaved edits visible until reload.
- **Read-only.** Approved records are shown without edit controls.
- **Approve gating.** The approve button is disabled, with the note "Resolve the PII flag first", while `pii_flag` is true and `pii_review` is not set. The API enforces the same rule.
- **Language.** The interface is in English (reviewers are FTUSA staff). Producer content is shown as stored.

## Testing Decisions

- **Component tests (Vitest with Vue Test Utils)** against a mocked API client:
  - agent and reviewer values shown side by side;
  - a 409 shows the reload message and keeps edits;
  - approved records have no edit controls;
  - the tag editor offers only the 11 tags;
  - PII matches show with their context, and approve is disabled until the flag is resolved.
- **Seam 3:** the deployed smoke test approves a record through the API (UI testing beyond that is manual for the demo).

## Out of Scope

- The Athena join query view. Journey 3's join runs as the Athena named query ([#28 spec](28-athena-sync.md)).
- Bulk actions
