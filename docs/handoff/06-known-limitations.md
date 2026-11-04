# Known limitations and open decisions

## Known limitations

What to know before running Fair Exchange in production. Each links to its source.

- **Analytics over time** (decided 2026-11-04). Hidden counts can be recovered by comparing results as
  new records arrive; no sandbox rule prevents this. The production analytics should publish on a fixed
  schedule, round counts, or add noise ([#29](../specs/29-analytics-api.md)).
- **Long-term memory recall is switched off.** Memory is built, but recall of earlier conversations
  stays off behind one eligibility function until the decline policy is decided, so declined text
  cannot resurface ([memory](../specs/memory.md)).
- **AgentCore Gateway was deferred** until after the MVP. Tools stay in the agent process so the
  producer-ID scope rule keeps working; Gateway is the path for adding tools later, with that scope
  rule as the design constraint ([#13](../specs/13-conversation-steps.md)).
- **Peer examples use a structured query.** Moving them to the Knowledge Base is a planned expansion
  ([#16](../specs/16-peer-example-tool.md)).
- **The verifier proves provenance, not wording.** It checks that a claim's citation points to a real
  source and clause, not that the claim's wording matches that source
  ([#17](../specs/17-standards-grounding.md)).
- **The scope metric is evidence, not proof.** It shows zero leaks across the tested attacks; it is not
  proof that no leak is possible (spec #34, `docs/specs/34-negative-scope-tests.md`, pending).
- **Observability content capture.** The AgentCore spike found full prompts, responses and tool results
  in runtime logs with no expiry; the content-capture policy and log retention are resolved in the
  full-stack deploy ([ADR 0002](../adr/0002-agentcore-runtime-spike.md), spec #5 pending).
- **Code merged before its spec.** Any code that landed ahead of its spec and has not yet been changed
  to match is listed from the retro review; keep this current as those are reconciled.

## Open decisions

Every "Not decided" item across the specs, gathered by topic. These are not to be built or assumed
until the owning spec decides them. (The CI open-decisions check fails if a spec gains a "Not decided"
section not referenced here.)

### Conversation lifecycle
- The inactivity period and the maximum conversation lifetime
  ([#13](../specs/13-conversation-steps.md), [#25](../specs/25-chat-endpoint.md)).
- What outcome and record a conversation gets when it closes without any consent choice — leaving before
  the consent question, or after only an out-of-scope request
  ([#13](../specs/13-conversation-steps.md), [#19](../specs/19-consent-and-decline.md),
  [#21](../specs/21-out-of-scope.md), [#26](../specs/26-write-back.md)).
- How the record shows consent while a reopened playback is waiting for a new choice
  ([#19](../specs/19-consent-and-decline.md), [#26](../specs/26-write-back.md)).

### Consent, decline and memory
- What happens to stored conversation text and derived memories when a producer declines
  ([#19](../specs/19-consent-and-decline.md), [memory](../specs/memory.md)).
- The memory retention values for short-term events and long-term records, and when the deletion
  function is called ([memory](../specs/memory.md)).
- Which long-term memories are eligible for recall — the reason recall is switched off
  ([memory](../specs/memory.md)).

### Records and storage
- How long records are kept ([#26](../specs/26-write-back.md)).
- Whether records of conversations that are still open appear in Athena; the sync currently copies every
  record, with the filter kept in one place in the sync Lambda ([#28](../specs/28-athena-sync.md)).

### Identity and scope
- How callers sign in, and the deployed stand-in for it, which the deployed smoke test and the demo need
  before the chat endpoint runs end to end ([#11](../specs/11-identity.md),
  [#25](../specs/25-chat-endpoint.md)).

### Out of scope
- How the out-of-scope detection function decides ([#21](../specs/21-out-of-scope.md)).

### This handoff
- Any item the specs list as "Not decided" that is added after this package was assembled
  ([#39](../specs/39-handoff.md)); the checks below keep this list honest.
