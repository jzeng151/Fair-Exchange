# Specs

One spec per outline issue. The issue stays a short outline; the spec is the implementation contract.

## Index

| Issue | Spec | Area |
|---|---|---|
| #5 | [CDK stack and single-command deploy](05-cdk-stack.md) | infra |
| #7 | [Producer data and synthetic data generator](07-synthetic-data.md) | data |
| #8 | [Regional fact table](08-regional-fact-table.md) | data |
| #11 | [Identity contract](11-identity.md) | api |
| #12 | [Bedrock Guardrail in detect mode](12-guardrail.md) | agent, infra |
| #13 | [Conversation steps](13-conversation-steps.md) | agent |
| #14 | [Producer-record tool](14-producer-record-tool.md) | agent |
| #15 | [Regional-context tool](15-regional-context-tool.md) | agent |
| #16 | [Peer-example tool](16-peer-example-tool.md) | agent |
| #17 | [Standards grounding and citation verifier](17-standards-grounding.md) | agent |
| #18 | [Grounded response with enablement tone](18-grounded-response.md) | agent |
| #19 | [Consent and decline](19-consent-and-decline.md) | agent |
| #20 | [PII flagging](20-pii-flagging.md) | agent |
| #21 | [Out-of-scope handling](21-out-of-scope.md) | agent |
| #22 | [Spanish exchange and bilingual record](22-spanish-exchange.md) | agent |
| #23 | [Feedback capture](23-feedback-capture.md) | agent |
| #24 | [French exchange](24-french-exchange.md) | agent |
| #25 | [Chat endpoint](25-chat-endpoint.md) | api |
| #26 | [Write-back](26-write-back.md) | agent, api |
| #27 | [Review API](27-review-api.md) | api |
| #28 | [Athena sync and record table](28-athena-sync.md) | data, infra |
| #29 | [Analytics API](29-analytics-api.md) | api |
| #31 | [Reviewer view](31-reviewer-view.md) | web |
| #32 | ["Your record" view](32-your-record.md) | api, web |
| #33 | [Admin analytics dashboard](33-admin-dashboard.md) | web |
| #34 | [Negative scope tests](34-negative-scope-tests.md) | agent, eval |
| #35 | [Scripted scenarios and labeled set](35-scenarios-and-labels.md) | eval |
| #36 | [Evaluation with AgentCore Evaluations](36-eval-harness.md) | eval |
| #37 | [Seeded conversation records for the dashboard](37-seeded-records.md) | data |
| #39 | [Handoff package](39-handoff.md) | docs |
| #40 | [Timed clean redeploy and demo run-through](40-timed-redeploy.md) | infra |
| #41 | [Voice notes via Amazon Transcribe](41-voice-notes.md) | agent, web |
| — | [Conversation memory (shared contract)](memory.md) | agent, infra |

## Rules

- Build what the spec says. If a spec is wrong or missing something, open a PR that changes the spec first, and get it approved before building the change.
- Each shared contract is defined in exactly one spec, under a heading marked "shared contract owned here". Other specs link to it rather than restate it. Change a contract only in the spec that owns it.
- Items under "Not decided" are not to be built or assumed. Leave them to the configuration value or function the spec names.
- The vision and technical environment documents in `docs/requirements/` still apply. Where a spec changes a requirement, it says so and gives the date of the decision.
- Issues closed before their spec was written (#4, #30, and code merged ahead of #8, #15, #16, #31, #33) are reviewed against the specs in a retro review.

## Minimum demo set (decided 2026-11-04)

Build these first. Everything else is ranked behind them, and starts only when this set is on track. The list follows the vision document's Definition of Done.

- Conversation flow, records and chat API: #13, #19, #20, #22, #25, #26
- Retrieval and grounding: #14 to #18, #8, #12
- Review and the Athena join: #27, #28, #31
- Producer data: #7
- Scope tests, with the standalone adversarial runner: #34
- Scenarios S1 to S5 (drought, Spanish price drop, labor shortage, Spanish decline, PII) and the 15-account labeled set: #35
- One-command deploy, handoff and the timed redeploy: #5, #39, #40

Next if time allows: S6 and S7, the full eval harness (#36), memory (#59), analytics (#29, #33, #37), "your record" (#32). Then the stretch goals (#24, #41).

## Test seams (shared by all specs)

Tests check what a caller sees, not internals. There are three seams:

1. **Agent entrypoint.**
   - **How it's driven:** with `start`, `message`, `action` and `resume` requests, the way the chat API calls it.
   - **Unit tests:** use a scripted fake model (a custom Strands model subclass that returns pre-written outputs), fixture data, an in-memory stand-in for AgentCore Memory, and a local DynamoDB fake (moto) for records.
   - **Evals:** the same entrypoint runs against real Bedrock and AgentCore Memory, in the eval area.
2. **Lambda handlers.**
   - **How they're called:** with API Gateway REST events or DynamoDB stream events.
   - **Fakes:** AWS SDK clients are mocked (`aws-sdk-client-mock` in TypeScript, moto in Python). Identity uses a fake resolver.
3. **Deployed smoke test.** One scripted conversation through the deployed API, then an Athena query for its record.

The existing scope-guard test (no tool exposes producer or location parameters) stays and runs alongside.

**Prior art:** the record schema, schema parity, generated-types and citation verifier tests. They test behavior through the public function, with plain fixtures and no mocks of internals.

**Spike check (#4):** confirm the scripted fake model works as a Strands model subclass.
