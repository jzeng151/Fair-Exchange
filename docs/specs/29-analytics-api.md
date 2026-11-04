# Spec: Analytics API (#29)

Status: approved for build, 2026-11-04. Should-have: start only once the must-haves are on track (decided 2026-11-04).

## Problem Statement

The client asked for an admin dashboard with breakdowns of the collected data. Aggregates over producer records carry privacy risk:
- small groups can identify a producer;
- declined conversations must not contribute narrative data;
- unreviewed agent output should not be presented as evidence by default.

## Solution

An admin-only route that runs fixed Athena queries over the records table and the seeded demo records ([#37 spec](37-seeded-records.md)). It returns breakdowns that follow #29's rules: consented records only, declines as counts only, reviewed records by default, and any breakdown cell under 5 hidden.

## User Stories

1. As an FTUSA admin, I want counts by challenge tag, language, entity type, consent scope, feedback and evidence, so that I can see what producers are raising.
2. As an FTUSA admin, I want the number of declined conversations, so that I see participation without any declined content.
3. As an FTUSA admin, I want reviewed records by default with an option to include pending ones, so that I know what has been checked.
4. As an FTUSA admin, I want the AI footprint (tokens by model, average per conversation), so that I can track the cost and energy of AI use (ADR 0001).
5. As a producer, I want any breakdown that could identify my organization hidden, so that my data stays private.
6. As an FTUSA admin, I want seeded demo data shown separately from live data, so that I do not mistake it for real activity.

## Implementation Decisions

- **Runtime.** TypeScript on Node.js 24, on the same REST API. The `admin` role is required ([#11 spec](11-identity.md)); others get 403.
- **Route.** `GET /analytics?include_pending=false`. Pending records are included only when `include_pending=true`.
- **Data.** Athena named queries, defined in CDK, over:
  - the live records table ([#28 spec](28-athena-sync.md)), counting only records with `closed_at` set;
  - the seeded records table ([#37 spec](37-seeded-records.md)).
- **Breakdowns:**
  - counts by effective tag, language, entity type, consent scope, feedback value and evidence marker, over completed records with granted consent;
  - declined count only;
  - AI footprint from `ai_usage` ([#26 spec](26-write-back.md)): total input and output tokens per model, and the average per conversation.
- **Suppression (decided 2026-11-04: close every known way to recover hidden counts).**
  - **Live counts only.** Suppression is applied to live counts. Seeded demo counts are never mixed in; they are returned as a separate `seeded` series ([#37 spec](37-seeded-records.md)).
  - **Small cells.** Any live cell with a count from 1 to 4 is returned as `{"suppressed": true}`, never as a number.
  - **Second cell.** If a breakdown has exactly one suppressed cell, the next-smallest cell in that breakdown is also suppressed, so the hidden one can't be worked out from a total or from another breakdown.
  - **Totals.** No breakdown returns a total. The single overall count of completed records is returned once and is itself suppressed if it is 1 to 4.
  - **Pending toggle.** With `include_pending=true`, a cell is also suppressed if its pending-only count (all minus reviewed) is 1 to 4, so comparing the two views reveals nothing.
- **Response.** One JSON object with a `live` and a `seeded` section, each holding every breakdown, plus the filters applied.
- **Latency.** The queries run on request, in parallel, with a 20-second limit. If any query times out or fails, the route returns 503 with a retry message, and nothing partial is returned.

## Testing Decisions

- **Seam 2 (Lambda handler)** with the Athena client mocked:
  - non-admins get 403;
  - live counts 1 to 4 are suppressed;
  - a breakdown with one suppressed cell has a second cell suppressed;
  - no breakdown returns a total;
  - seeded counts are returned separately and never added to live cells;
  - with `include_pending`, a cell whose pending-only count is 1 to 4 is suppressed;
  - a query timeout returns 503;
  - declined records appear only as a count;
  - pending records are excluded by default;
- **Query tests** against fixture data in Athena during the deployed smoke test: the breakdowns match the fixture counts.

## Out of Scope

- Region-level aggregation (out of scope per the vision document)
- Drill-down to individual records
