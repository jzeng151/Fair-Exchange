# Spec: Standards grounding and citation verifier (#17)

Status: approved for build, 2026-11-04.

## Problem Statement

Every insight and peer example FEX gives must be traceable: to a source the tools actually returned, and to a real APS or FPS clause that relates to it. Without a shared contract for what a tool returns and what counts as a source, each tool invents its own shape and the verifier cannot check them. A clause that merely exists in APS or FPS proves little. It should be one the standards lookup actually found relevant to this producer's challenge.

## Solution

All data tools return items in one shape, each with a citable `source` label. A standards tool finds the clauses related to the confirmed challenge through an Amazon Bedrock Knowledge Base. The existing deterministic verifier is extended in two ways:
- a cited clause must have been returned by the standards tool in this conversation;
- a claim that uses directive language fails.

Each claim can be checked on its own, so the answer can stream claim by claim ([#13 spec](13-conversation-steps.md)).

## User Stories

1. As a producer, I want every fact FEX gives me to name where it came from, so that I can judge how much to trust it.
2. As a producer, I want each insight linked to the Fair Trade standard clause it relates to, so that I see how it connects to my certification.
3. As a producer, I want FEX never to show a fact it cannot trace to a source, so that I am not misled.
4. As an FTUSA reviewer, I want cited clauses to be ones the standards lookup found relevant, not just any real clause, so that citations are meaningful.
5. As an FTUSA reviewer, I want claims phrased as instructions rejected, so that FEX informs rather than directs.
6. As an FTUSA engineer, I want one item shape for every data tool, so that the verifier and the answer writer treat all sources the same way.
7. As an FTUSA engineer, I want the standards Knowledge Base loaded during deploy, so that one-command deploy produces a working lookup.
8. As an FTUSA engineer, I want verification to stay deterministic, with no model involved, so that it can be tested exactly.

## Implementation Decisions

### Data tool contract (shared contract owned here)

Every data tool (producer record, regional context, peer examples, standards):
- **Scope.** It is a Strands tool with tool context. It reads the producer ID, profile, confirmed tags, crops and entity type from the request context and conversation state. It takes **no model-settable arguments**, so the model can call it but cannot steer what it reads. The scope-guard test is tightened to assert that every data tool's input schema has no properties at all. Today's test only rejects certain parameter names, which a tool like the merged peer tool's `challenge` parameter passes.
- **Step gating.** It refuses outside the `respond` step ([#13 spec](13-conversation-steps.md)).
- **Who calls it (decided 2026-11-04).** The model calls the tools as a Strands agent. Before any claim is written, code checks that all four data tools ran in this `respond` step and calls any the model skipped. Each backstopped call is noted in the decision log (code `tool_backstopped`).
- **Result shape.** It returns a list of items. Each item has:
  - `source`: a citable label, unique per fact or record, ending in the item's stable ID in brackets, e.g. `CHIRPS v2.0 rainfall anomaly, Cauca, 2024-2025 [RF-0142]`. The model must copy it exactly.
  - `kind`: `producer_record`, `regional`, `peer` or `standard`.
  - `text`: a plain-English statement of the fact.
  - `period`: the time span, or null.
  - `strength`: `exact`, `nearest` or `limited`.
  - `data`: tool-specific structured fields.
- **Session evidence.** Every item's `source` and `kind` are added to the conversation's session evidence as it is returned. This extends the existing `SessionEvidence.record_tool_result` to keep the kind.
- **Empty results.** A tool that finds nothing returns an empty list, not an error. Empty results lead to the limited-evidence path ([#13 spec](13-conversation-steps.md)).

### Standards tool

- **Knowledge Base.** Amazon Bedrock Knowledge Base with an Amazon S3 Vectors vector store.
  - **Documents:** one per APS or FPS clause, generated from the merged standards loader's clause table. Each holds the clause text with metadata `clause_id` and `standard`.
  - **Embedding model:** Amazon Titan Text Embeddings V2.
- **Query.** The confirmed playback's English summary plus its tags. For English conversations, where `summary_english` may be empty, it uses `summary_original`. Querying in English keeps results the same for Spanish conversations.
- **Results.** The top 5 clauses. Each item carries `clause_id` in `data`, the clause text as `text`, and the clause ID as `source`.
- **Recording.** The returned clause IDs are recorded in a separate `clauses` set in the session evidence. This is a small addition to `SessionEvidence`.
- **Chunking.** None (one chunk per clause document), so the top 5 results are 5 distinct clauses.
- **Loading during deploy.**
  - CDK defines the Knowledge Base and an asynchronous custom resource that starts an ingestion job and polls until it completes, with a 20-minute limit. Ingestion failure or timeout fails the deploy. Without this, one-command deploy creates an empty Knowledge Base.
  - The custom resource takes a content hash of the clause documents as a property, so changed clauses trigger re-ingestion on the next deploy.
  - Deleting the stack deletes the Knowledge Base; the custom resource does nothing on delete.

### Verifier changes

These extend the merged verifier.
- **Per-claim check.** A public function checks one claim. The whole-answer `verify` uses it.
- **Clause rule.** A claim's `standard_clause` must exist in APS or FPS (as today) **and** be in the session's `clauses` set.
- **Section rule.** An insight must cite a source of kind `producer_record` or `regional`. A peer example must cite a source of kind `peer`.
- **Reason codes.** Each failure carries a fixed reason code (`unknown_source`, `wrong_source_kind`, `unknown_clause`, `clause_not_retrieved`, `directive_language`, `malformed`), alongside today's readable reason. The decision log records only the codes ([#26 spec](26-write-back.md)).
- **Directive language.** Claim text containing a directive phrase fails, with the reason "directive language". The phrases are kept in one shared list, in English, Spanish and French ([#24](24-french-exchange.md)), also used by the eval tone check: e.g. "you should", "we recommend", "the best option", "usted debe", "le recomendamos", "la mejor opción", "vous devriez", "nous recommandons", "la meilleure option", "il faut que vous".
- **Unchanged:** no model involvement, and dropping claims that still fail after the last retry. How retries work with streaming is in the [#18 spec](18-grounded-response.md).
- **What it proves.** The check proves provenance: each claim cites a real, retrieved source of the right kind and a retrieved clause. It does not prove the claim's wording matches the cited fact, or that the clause is the best fit. Those are checked by evals and by the reviewer.

## Testing Decisions

- **Verifier (public function tests, extending the existing verifier tests):**
  - a real clause not returned by the standards tool fails;
  - a returned clause passes;
  - a directive phrase in English or Spanish fails;
  - an insight citing a peer source, or a peer example citing a regional source, fails with `wrong_source_kind`;
  - the per-claim check and the whole-answer check agree.
- **Seam 1 (agent entrypoint),** with a fake Knowledge Base retriever behind the same interface:
  - standards items reach session evidence;
  - the query uses the English summary for a Spanish conversation;
  - the tool refuses outside `respond`;
  - when the model skips a tool, code calls it before claims are written, and the decision log records `tool_backstopped`;
  - no data tool exposes an input property (tightened scope-guard test).
- **Seam 3 (deployed smoke test):** after deploy, a known challenge returns at least one clause from the real Knowledge Base.
- **Prior art:** the existing verifier and standards lookup tests.

## Out of Scope

- The Trade Standard (out of scope per the vision document)
- Peer examples through the Knowledge Base ([#16 spec](16-peer-example-tool.md) notes it as a later expansion)

## Further Notes

### Decisions made while writing this spec

- Data tools take no model-settable arguments; they read everything from the request context and conversation state.
- A cited clause must have been returned by the standards tool in this conversation, not merely exist.
- Directive phrases fail the deterministic check, as well as being scored in evals.

### Spike checks (#4)

- S3 Vectors as a Knowledge Base store is available in `us-west-2`, and the CDK constructs support it
- Whether S3 Vectors needs `AMAZON_BEDROCK_TEXT` and `AMAZON_BEDROCK_METADATA` set as non-filterable metadata keys to stay under the filterable-metadata size limit
