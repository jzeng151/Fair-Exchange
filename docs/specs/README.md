# Specs

One spec per outline issue. The issue stays a short outline; the spec is the implementation contract.

## Rules

- Build what the spec says. If a spec is wrong or missing something, open a PR that changes the spec first, and get it approved before building the change.
- Each shared contract is defined in exactly one spec, under a heading marked "shared contract owned here". Other specs link to it rather than restate it. Change a contract only in the spec that owns it.
- Items under "Not decided" are not to be built or assumed. Leave them to the configuration value or function the spec names.
- The vision and technical environment documents in `docs/requirements/` still apply. Where a spec changes a requirement, it says so and gives the date of the decision.
- Specs for retrieval tools and grounding, PII, review and analytics, the web UI, evaluation, and deployment come in a later batch.

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
