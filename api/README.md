# api/

TypeScript Lambda handlers behind API Gateway. Use Lambda Powertools for logging, tracing and idempotency.

| Handler | Route | Purpose | Issue |
|---|---|---|---|
| `conversations.ts` | `POST /conversations`, `POST /conversations/{id}/messages`, `POST /conversations/{id}/actions` (streamed), `GET /conversations/{id}`, `GET /conversations` | Chat API. Resolves the producer from the login (never the request), checks conversation ownership, takes the turn lock, streams the agent's events | #25 |
| `sweep.ts` | scheduled, every 15 minutes | Closes idle conversations and reconciles ones the agent already closed | #25 |
| `writeBack.ts` | (invoked on consent) | Comprehend PII flag (never redact) → exactly one DynamoDB record (idempotent) | #26 |
| `review.ts` | `GET/PATCH /records` | Fair Trade USA review: list, correct tags/summary, approve | #27 |
| `analytics.ts` | `GET /analytics` | Dashboard numbers, including AI footprint | #29 |

Record types are generated from `agent/src/fex/models.py`. Do not hand-edit them.

## Chat API (#25)
Contract: [`docs/specs/25-chat-endpoint.md`](../docs/specs/25-chat-endpoint.md). Code lives in `src/core/`; `src/handlers/` is thin wiring.
Run `npm test` for the handler tests (Vitest, in-memory store, scripted agent).
Environment variables:
| Variable | Used by | Meaning |
|---|---|---|
| `CONVERSATIONS_TABLE` | chat handlers, sweep | Conversations table (partition key `conversation_id`; index `producer_id-created_at-index` on `producer_id`, `created_at`) |
| `AGENT_RUNTIME_ARN` | chat handlers, sweep | AgentCore runtime to invoke |
| `INACTIVITY_MINUTES` | sweep | Inactivity period. Not decided in the spec, so it has no default. |
Identity comes from `src/core/identity.ts` (`resolveCaller`). It is a placeholder that reads `producerId` from the API Gateway authorizer context, until FTUSA chooses how callers sign in (#11).

## Analytics API (#29)
Contract: [`docs/specs/29-analytics-api.md`](../docs/specs/29-analytics-api.md). Code lives in `src/analytics/`; `src/handlers/analytics.ts` is thin wiring.

`GET /analytics?include_pending=false`: admin role required (403 otherwise, 401 if unidentified). Pending records are included only when `include_pending=true`; any other value gives the reviewed-only view.

The handler loads the fixed SQL once per container from the Athena named queries defined in CDK (`infra/lib/analytics-queries-stack.ts`, matched by name), runs all four queries in parallel in the workgroup, and allows 20 seconds in total. If any query fails or times out it returns 503 with a retry message and nothing partial; unfinished queries are stopped.

| Variable | Meaning |
|---|---|
| `ATHENA_WORKGROUP` | Athena workgroup (`fex`, from the Athena sync stack) |
| `ANALYTICS_NAMED_QUERY_IDS` | Comma-separated named query IDs: the `AnalyticsNamedQueryIds` output of `FairExchangeAnalyticsQueries` |

Role checks use `resolveIdentity` in `src/core/identity.ts`, which returns `{user_id, roles, producer_id?}` (#11). Like `resolveCaller`, it is a placeholder that reads `userId` and comma-separated `roles` from the API Gateway authorizer context only, until the sign-in method is decided.

### Response
```json
{
  "filters": { "include_pending": false, "consent_scopes": ["internal", "internal_and_outward"], "live_closed_only": true },
  "live": {
    "completed": 42,
    "declined": 9,
    "by_tag": { "water": 12, "health": { "suppressed": true }, "soil and land": { "suppressed": true } },
    "by_language": { "en": 20, "es": 22 },
    "by_entity_type": { "cooperative": 42 },
    "by_consent_scope": { "internal": 30, "internal_and_outward": 12 },
    "by_feedback": { "yes": 25, "somewhat": 9, "none": 8 },
    "by_evidence": { "full": 35, "limited": 7 },
    "ai_footprint": [{ "model_id": "...", "input_tokens": 120000, "output_tokens": 18000 }]
  },
  "seeded": { "same keys as live": "never suppressed" }
}
```
- `completed` counts completed records with granted consent; `declined` is a count only. The `by_*` breakdowns are over completed records with granted consent. Tags are effective tags (the reviewer's if set, else the agent's); `none` in `by_feedback` means no feedback was given. A cell appears only if it has records in at least one view.
- Live counts include only closed records (`closed_at` set). A record counts as reviewed only when `review_status` is `reviewed`; declined records carry no review status, so they count as pending and appear only with `include_pending=true`.
- No totals, and no AI footprint conversation count or average: `ai_footprint` is total input and output tokens per model only, over all closed live records (both statuses, any review status).
- `seeded` holds the seeded demo records (#37) in the requested view. They are never suppressed, never added to live cells, and never affect which live cells are hidden. The seeded Glue table (`fex.records_seeded`, over `records-seeded/`) is not defined yet; that name is assumed.

### Suppression (`src/analytics/suppression.ts`)
Applied to live counts only, always to the reviewed-only and include-pending views together, whichever one is requested:
1. A cell with a count of 1 to 4 in either view is hidden, and so is a cell whose pending-only count (include-pending minus reviewed) is 1 to 4.
2. A cell hidden in either view is hidden in both.
3. In each view, a breakdown with exactly one hidden cell also hides its next-smallest cell (a non-zero one if there is one).
4. Steps 2 and 3 repeat until every breakdown has no hidden cells or at least two, in both views.

Completed vs declined is one two-cell breakdown under all of these rules: if either is hidden, both are. A hidden cell is always `{"suppressed": true}`, never a number.

Tests: `src/analytics/suppression.test.ts` (the rules, plus property checks over random count tables) and `src/handlers/analytics.test.ts` (seam 2, Athena client mocked with `aws-sdk-client-mock`, fake identity resolver).
