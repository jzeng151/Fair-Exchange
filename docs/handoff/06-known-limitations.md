# Known limitations and open decisions

## Known limitations

What to know before running Fair Exchange in production. Each links to its source.

- **Analytics over time** (decided 2026-11-04). Hidden counts can be recovered by comparing results as
  new records arrive; no sandbox rule prevents this. The production analytics should publish on a fixed
  schedule, round counts, or add noise ([#29](../specs/29-analytics-api.md)).
- **Persistent memory is configured, not on by default.** `default_engine()` uses AgentCore Memory when
  `FEX_MEMORY_ID` is set, so a conversation survives a runtime replacement; without it the agent falls back
  to an in-process `InMemoryStateStore` and state is lost on replacement ([memory spec](../specs/memory.md)).
  The sandbox deploy sets `FEX_MEMORY_ID`. Memory keeps conversation events and the long-term strategies
  on, and does not delete anything when a producer declines; that policy is FTUSA's to decide (see
  "Decisions for FTUSA" below). Long-term recall of earlier conversations stays off behind one eligibility
  function until it is decided, so declined text cannot resurface.
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
  in runtime logs with no expiry ([ADR 0002](../adr/0002-agentcore-runtime-spike.md)). The sandbox runtime
  turns content capture off and keeps logs 30 days; a CloudWatch Logs Insights search of a real
  conversation found no message content. Whether content may ever appear in logs, and the retention
  period, remain FTUSA's decisions ([#5](../specs/05-cdk-stack.md)).
- **Code merged before its spec.** Any code that landed ahead of its spec and has not yet been changed
  to match is listed from the retro review; keep this current as those are reconciled.

## Decided

- **Inactivity period and maximum conversation lifetime** (decided 2026-11-04 for the sandbox and pilot):
  a conversation closes after 120 minutes without a message, and the runtime session ends after
  1440 minutes (24 hours) ([#13](../specs/13-conversation-steps.md),
  [#25](../specs/25-chat-endpoint.md), [deploy](02-deploy.md)).
- **Deployed sign-in stand-in** (decided 2026-11-04, sandbox demo only): a shared passcode plus a producer
  from the eval scenarios' allow-list, checked by an API Gateway Lambda authorizer. Anyone with the passcode
  can act as any of those synthetic producers. A separate admin passcode grants the `admin` role for
  analytics only. Production sign-in replaces both
  ([#11](../specs/11-identity.md), [#25](../specs/25-chat-endpoint.md)).

## Decisions for FTUSA

Privacy and administration choices are FTUSA's to make after handoff. Until then the sandbox runs with
the current behavior below; each row stays in the open list that follows until FTUSA decides it.

### Privacy

| Decision | Current sandbox behavior |
|---|---|
| What happens to stored text and derived memories on decline ([#19](../specs/19-consent-and-decline.md), [memory](../specs/memory.md)) | Nothing is deleted; the record shows the decline |
| Memory retention for events and long-term records ([memory](../specs/memory.md)) | Short-term events expire after 7 days (the stack's sandbox value); long-term records have no expiry; no deletion call is made |
| Which long-term memories may be recalled ([memory](../specs/memory.md)) | Recall is off |
| Whether message content may appear in logs ([#5](../specs/05-cdk-stack.md)) | Content capture is off and verified |
| Log retention ([#5](../specs/05-cdk-stack.md)) | 30 days, passed as `LOG_RETENTION_DAYS` |
| How long records are kept ([#26](../specs/26-write-back.md)) | No expiry on the DynamoDB records or their Athena copy; only Athena query results expire (30 days) |
| Outcome of a conversation that closes without a consent choice ([#13](../specs/13-conversation-steps.md), [#19](../specs/19-consent-and-decline.md)) | Not built; see the open list |
| How the record shows consent while a reopened playback waits ([#19](../specs/19-consent-and-decline.md)) | Not built; see the open list |
| Whether open conversations appear in Athena ([#28](../specs/28-athena-sync.md)) | Every record is copied |

### Administration

| Decision | Current sandbox behavior |
|---|---|
| Production sign-in, expected to be FTUSA's Okta ([#11](../specs/11-identity.md)) | The demo passcode stand-in only; synthetic scenario producers |
| Who may invoke the runtime | The chat and sweep Lambda roles are granted it; account administrators can also invoke it |
| CDK bootstrap permissions | The default bootstrap, which grants CloudFormation `AdministratorAccess`; FTUSA may scope it down |

## Open decisions

Every "Not decided" item across the specs, gathered by topic. These are not to be built or assumed
until the owning spec decides them. The CI open-decisions check fails if a spec gains or loses a
"Not decided" item without this list and the manifest below being updated to match.

<!-- open-decisions-manifest
05-cdk-stack.md: 2
13-conversation-steps.md: 1
19-consent-and-decline.md: 3
21-out-of-scope.md: 2
26-write-back.md: 3
28-athena-sync.md: 1
40-timed-redeploy.md: 1
memory.md: 3
-->

The count beside each spec in the manifest comment above is how many "Not decided" items that spec
currently has; it is checked against the specs in CI.

### Conversation lifecycle
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

### Out of scope
- How the out-of-scope detection function decides ([#21](../specs/21-out-of-scope.md)).
### Deployment and logging
- The log-group retention period: a required deploy-time value with no default, chosen per deploy
  ([#5](../specs/05-cdk-stack.md)).
- Whether message content may appear in AgentCore logs at all: content capture is a configuration value,
  and ADR 0002 found the Strands tracer still logs content when the documented setting is off, so whoever
  turns it off must verify the result ([#5](../specs/05-cdk-stack.md)).
- How the timed-redeploy scenarios sign in as their producers ([#40](../specs/40-timed-redeploy.md)). The
  sign-in stand-in it waited on is now decided ([#11](../specs/11-identity.md)), so this can be settled.

### This handoff
- Any item the specs list as "Not decided" that is added after this package was assembled
  ([#39](../specs/39-handoff.md)); the checks below keep this list honest.
