# Spec: Review API (#27)

Status: approved for build, 2026-11-04.

## Problem Statement

Agent output is not evidence until a person has reviewed it. An Impact, Research & Learning reviewer needs to:
- list records waiting for review;
- see everything about each one;
- correct tags, summaries and PII decisions;
- approve it.

Corrections must never overwrite the agent's original output, so that tag accuracy can be measured. A reviewer must not edit a record that is still changing.

## Solution

Reviewer-only routes on the existing REST API read and update records in DynamoDB. They follow the record write rules ([#26 spec](26-write-back.md)): validation, a version and closed-conversation check, and only the reviewer fields. The Streams sync carries every change to Athena ([#28 spec](28-athena-sync.md)).

## User Stories

1. As a reviewer, I want a list of completed records from closed conversations, pending first, so that I know what to review.
2. As a reviewer, I want to filter by review status, PII flag and limited evidence, so that I can prioritize.
3. As a reviewer, I want to open a record and see everything on it, so that I can judge it. That covers summaries in both languages, tags, insights and peer examples with citations, earlier answers, consent history, PII matches with context, evidence marker and decision log.
4. As a reviewer, I want to correct tags and summaries without losing the agent's version, so that both are kept.
5. As a reviewer, I want to confirm or clear a PII flag, so that false alarms are resolved.
6. As a reviewer, I want to approve a record, so that it counts as reviewed evidence.
7. As a reviewer, I want a clear message if someone else changed the record while I was editing, so that I do not overwrite their work.
8. As an FTUSA engineer, I want only reviewers to reach these routes, so that producers cannot see other producers' records.
9. As an FTUSA engineer, I want review changes to appear in Athena automatically, so that review status stays consistent everywhere.

## Implementation Decisions

- **Runtime.** TypeScript on Node.js 24, on the same REST API as the chat endpoint ([#25 spec](25-chat-endpoint.md)). Normal (non-streaming) integration.
- **Access.** The caller must have the `reviewer` role from the identity-resolution function ([#11 spec](11-identity.md)). Others get 403.
- **Routes:**

| Method and path | Purpose |
|---|---|
| `GET /records` | Closed completed records. Filters: `review_status`; `pii` (`unresolved` means flagged with no review decision, `any` means flagged at all); `evidence`. Returns record ID, closed time, language, entity type, effective tags, review status, PII flag, PII review, evidence and version. |
| `GET /records/{id}` | The full record. 404 if missing, declined or not closed. |
| `PATCH /records/{id}` | Body: `version` plus any of `reviewer_tags`, `reviewer_summary_original`, `reviewer_summary_english`, `pii_review`. |
| `POST /records/{id}/approve` | Body: `version`. Sets `review_status` to `reviewed`, `reviewed_by` and `reviewed_at`. Returns 409 with reason `pii_unresolved` if `pii_flag` is true and `pii_review` is not set. |

- **Write rules:**
  - Writes are conditioned on `version` and `closed_at` being set, not on `producer_id` ([#26 spec](26-write-back.md)). A version mismatch returns 409 with the current version.
  - Every write validates the full record against the generated JSON Schema before writing.
  - Every write sets `updated_at` and increments `version`.
  - Only the fields above, plus the review fields, can change. The agent's fields never change.
- **After approval.** An approved record is read-only in the MVP; `PATCH` returns 409.
- **Listing.** A filtered scan of the records table. That is adequate at sandbox scale; an index is a later optimization.
- **Logs.** Record ID, reviewer, route and status only. No narrative text.

## Testing Decisions

- **Seam 2 (Lambda handlers)** with `aws-sdk-client-mock` and a fake identity resolver:
  - non-reviewers get 403;
  - open and declined records are excluded and return 404;
  - a correction writes only reviewer fields;
  - a stale version returns 409;
  - an invalid tag fails schema validation;
  - approve sets the review fields;
  - approve with an unresolved PII flag returns 409 `pii_unresolved`;
  - the `pii=unresolved` filter excludes records whose flag was confirmed or cleared;
  - a `PATCH` after approval returns 409.
- **Seam 3:** after a reviewer approves a demo record, Athena shows `reviewed`.

## Out of Scope

- Review queue assignment, notifications (out of scope per the vision document), reopening approved records

## Further Notes

### Decisions made while writing this spec

- Approved records are read-only in the MVP.
- Listing uses a scan rather than an index.
