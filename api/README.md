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
