# Spec: Handoff package (#39)

Status: approved for build, 2026-11-04.

## Problem Statement

FTUSA Digital Technology will own this system after the hackathon and must redeploy it in their own account. The vision document requires a handoff package: record schema, tool contracts, deployment instructions, the synthetic data generator, and a stand-in to target mapping. If these are written at the end from memory, they will be incomplete and wrong in places.

## Solution

The handoff lives in `docs/handoff/` as a small set of documents. Each links to its source of truth (specs, generated schema, CDK outputs) rather than copying it. Contributors update it in the same PR as any interface change, per CONTRIBUTING, so the final step is a check, not a writing marathon. The timed redeploy (#40) is the proof that it works.

## User Stories

1. As an FTUSA engineer, I want one starting page that tells me what to read in what order, so that I can get oriented quickly.
2. As an FTUSA engineer, I want deploy instructions that a person who wasn't at the hackathon can follow, so that we can redeploy without help.
3. As an FTUSA engineer, I want the record schema, tool contracts and API routes in one place, so that we can integrate with our own systems.
4. As an FTUSA engineer, I want a table mapping each sandbox stand-in to its production target, so that I know what to replace.
5. As an FTUSA engineer, I want the known limitations and open decisions listed, so that nothing surprises us in production.
6. As an FTUSA engineer, I want the data generator documented, so that we can rebuild the data with our own sample.

## Implementation Decisions

- **Documents in `docs/handoff/`:**
  1. **Start here:** what Fair Exchange is, a reading order, and links to the vision document, the specs index and the ADRs.
  2. **Deploy:** the single-command deploy ([#5](05-cdk-stack.md)), prerequisites (model access, Transaction Search), the required configuration values with their meaning, stack outputs, teardown, and the measured redeploy time from #40.
  3. **Interfaces:**
     - the record schema (link to the generated JSON Schema and TypeScript types);
     - the data tool contract and each tool ([#14](14-producer-record-tool.md) to [#17](17-standards-grounding.md));
     - the agent request, action and event schemas ([#13](13-conversation-steps.md));
     - API routes and roles ([#11](11-identity.md), [#25](25-chat-endpoint.md), [#27](27-review-api.md), [#29](29-analytics-api.md), [#32](32-your-record.md)).
  4. **Data:** the generator ([#7](07-synthetic-data.md)), the vocabulary mapping table, the survey allowlist, the regional fact table and how to replace each with FTUSA data.
  5. **Stand-in to target mapping:**

| Sandbox stand-in | Production target |
|---|---|
| Athena over S3 | Redshift ("Atlas") |
| DynamoDB records table | FTUSA's production record store |
| Test sign-in stand-in | Okta SSO |
| Regional fact table (pre-extracted) | Live or scheduled open-data pipelines |
| Producer table (sample plus synthetic) | Salesforce and warehouse producer data |
| Bedrock Knowledge Base on S3 Vectors | Same service, FTUSA's account |
| Seeded demo records | Removed |

  6. **Known limitations:**
     - **Analytics over time (decided 2026-11-04).** Hidden counts can be recovered by comparing results as new records arrive. No sandbox rule prevents this. FTUSA's production version should publish on a fixed schedule, round counts, or add noise.
     - Long-term recall is built but switched off until the decline policy is decided ([memory spec](memory.md)).
     - AgentCore Gateway was deferred until after the MVP. Tools stay in-process because of the scope rule (#13).
     - Peer examples use a structured query. Moving them to the Knowledge Base is a planned expansion ([#16](16-peer-example-tool.md)).
     - The verifier proves provenance, not that a claim's wording matches its source ([#17](17-standards-grounding.md)).
     - Code merged before its spec and not yet changed to match, listed from the retro review.
  7. **Open decisions:** every "Not decided" item across the specs, gathered into one list by topic, each linking to its spec.
- **Keeping it current.** A PR that changes an interface updates the matching handoff document (CONTRIBUTING). The PR template already has this checkbox.
- **Final check.** At #40, the person running the redeploy follows only the handoff documents, and records every step that was missing or wrong. Those gaps are fixed before close.

## Testing Decisions

- **Link check:** a CI step fails if a relative link in `docs/handoff/` or `docs/specs/` points to a missing file.
- **Open-decisions check:** the open-decisions list contains every "Not decided" heading's items, verified by a small script that compares them.
- **Usability:** the #40 run-through, above.

## Out of Scope

- Production runbooks, alerting and on-call (FTUSA's)
- Training material (program deliverable, not build deliverable)
