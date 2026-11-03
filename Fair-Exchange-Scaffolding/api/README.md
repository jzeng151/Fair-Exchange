# api/

TypeScript Lambda handlers behind API Gateway. Use Lambda Powertools for logging, tracing and idempotency.

| Handler | Route | Purpose | Issue |
|---|---|---|---|
| `chat.ts` | `POST /chat` | Takes the producer's message; sets `producerId` **from the login**, never the request body; calls the FEX runtime | #25 |
| `writeBack.ts` | (invoked on consent) | Comprehend PII flag (never redact) → exactly one DynamoDB record (idempotent) | #26 |
| `review.ts` | `GET/PATCH /records` | Fair Trade USA review: list, correct tags/summary, approve | #27 |
| `analytics.ts` | `GET /analytics` | Dashboard numbers, including AI footprint | #29 |

Record types are generated from `agent/src/fex/models.py`. Do not hand-edit them.
