# Stand-in → target mapping

Fair Exchange runs on sandbox stand-ins so it could be built before FTUSA's production systems were
wired in. Each row is what to replace, and with what. In every case the interface stays the same: the
[tool contracts](tool-contracts.md) and the [API routes](03-interfaces.md) do not change when a
stand-in is swapped for its target — only the loader, store or resolver behind it.

| Sandbox stand-in | Production target |
|---|---|
| Athena over S3 | Redshift ("Atlas") |
| DynamoDB records table | FTUSA's production record store |
| Test sign-in stand-in | Okta SSO |
| Regional fact table (pre-extracted) | Live or scheduled open-data pipelines |
| Producer table (sample plus synthetic) | Salesforce and warehouse producer data |
| Bedrock Knowledge Base on S3 Vectors | Same service, FTUSA's account |
| Seeded demo records | Removed |

Notes on the swaps that touch a contract-owning seam:

- **Sign-in.** The identity-resolution function ([#11](../specs/11-identity.md)) is the only place that
  reads identity. Replacing the test stand-in with Okta changes that one function; no handler changes.
  The deployed sign-in stand-in is itself still "Not decided" (see
  [open decisions](06-known-limitations.md#open-decisions)).
- **Records store.** The record schema ([#26](../specs/26-write-back.md)) is the contract; moving from
  DynamoDB to the production store keeps the schema and the review/"your record" routes.
- **Producer and regional data.** Swap the loaders in `fx_data` (see [Data](04-data.md)); the data-tool
  contracts are unchanged.
- **Retrieval.** Peer examples currently use a structured query, with the Knowledge Base as a planned
  expansion ([#16](../specs/16-peer-example-tool.md)); standards grounding already uses a Knowledge Base
  ([#17](../specs/17-standards-grounding.md)).
- **Seeded demo records** exist only to populate the dashboard for the demo
  ([#37](../specs/37-seeded-records.md)); remove them in production.
