# Handoff package

## Sandbox scaffold deployment

The hosting slice for issues #5 and #30 deploys the Vue website.
Follow [the deployment instructions](../../infra/README.md). The website publishing
workflow does not deploy API, AgentCore, or data resources. See the
[remaining work for #5](sandbox-deployment.md#remaining-work-for-issue-5) for the
full-stack deployment checklist and the completed AgentCore spike.

The GitHub Actions workflow implements the checks in #10 and adds OIDC-based
website publishing after successful checks on `main`. See the GitHub Actions
section in the deployment instructions for permission scope and setup.

Build validation uses `npm run build` in `web` and `npx tsc --noEmit` plus
`npx cdk synth` in `infra`. The deployment script verifies the account ID before
creating resources and publishes only `web/dist`. No source documents, sample
datasets, credentials, or producer records are uploaded to the website bucket.

## Remaining handoff work

What Fair Trade USA engineering needs to redeploy and run Fair Exchange in their own account (issue #39):

- [ ] Record schema (generated from `agent/src/fex/models.py`)
- [ ] Tool interface contracts (inputs, outputs, scope rule)
- [ ] API routes (chat routes are documented below; review and analytics come with #27 and #29)
- [ ] CDK outputs and deploy steps (timed clean redeploy, #40)
- [ ] Synthetic data generator and loading instructions
- [ ] Stand-in → target mapping (Athena → Redshift "Atlas", DynamoDB → production store, test identities → Okta)
- [ ] Known limitations

## Chat API routes (#25)
Contract: `docs/specs/25-chat-endpoint.md`. Code: `api/src/core/`, `api/src/handlers/conversations.ts`, `api/src/handlers/sweep.ts`.
| Route | Streams | Notes |
|---|---|---|
| `POST /conversations` | yes | Server creates the conversation ID. First event is `{ "type": "conversation", "conversationId": ... }`. |
| `POST /conversations/{id}/messages` | yes | Body `{ "text": string }`, 1 to 4,000 characters |
| `POST /conversations/{id}/actions` | yes | Body `{ "action": string, "args": object }` |
| `GET /conversations/{id}` | no | Agent `resume` output plus `conversationId` and `status` |
| `GET /conversations` | no | `{ "conversations": [{ conversationId, createdAt, status }] }`, newest first |
Streams are `application/x-ndjson`. Errors: 400 (unknown field, or any producer or conversation ID in the body), 401 (caller not identified), 404 (missing or someone else's conversation, same response), 409 (conversation closed, or a turn is in progress).
Turn lock: each turn holds a lease (`lock_expires_at`, `lock_token`) taken before the response starts, so a 409 is a real HTTP 409. Agent calls are cut off at 290 s (Lambda timeout 300 s, lease 330 s), and only the holder's token can release the lock. `resume` calls (`GET /conversations/{id}` and the sweep) are cut off at 20 s, so a stalled agent is skipped rather than blocking the sweep.

Deploy inputs the stack must provide: the conversations table and index, `AGENT_RUNTIME_ARN`, the REST API with response streaming and a 5 minute timeout on the three POST routes, the 15 minute schedule for the sweep, and `INACTIVITY_MINUTES`. Only the chat handlers and the sweep may write the table or invoke the runtime. Until the stack is wired, these handlers are not deployed.

## Guardrail (#12)
Contract: `docs/specs/12-guardrail.md`. CDK: `infra/lib/guardrail.ts` (`FexGuardrail`, in the `FairExchange` stack). Agent: `agent/src/fex/guardrail.py`.
- **Policies:**
  - Denied topics: "Certification status and audit results" and "Worker grievances and complaints".
  - Content filters: SEXUAL, VIOLENCE, HATE, INSULTS, MISCONDUCT and PROMPT_ATTACK (input only).
  - Every action is `NONE` (detect).
  - No sensitive-information or contextual grounding policy.
- **Stack outputs:** `GuardrailId`, `GuardrailVersion`. A configuration change creates a new version on the next deploy.
- **Runtime wiring** (for the FEX runtime, #4/#5):
  - Set the env vars from `guardrail.runtimeEnvironment` (`FEX_GUARDRAIL_ID`, `FEX_GUARDRAIL_VERSION`).
  - Call `guardrail.grantApply(executionRole)` for `bedrock:ApplyGuardrail`.
  - The hello-world spike runtime is not wired.
- **Output text:** model replies are returned as structured output (tool-use input), which the Converse guardrail does not assess. FEX assesses that text with a detect-only `ApplyGuardrail` call (source `OUTPUT`) and logs findings the same way. This needs `bedrock:ApplyGuardrail` on the runtime role (`grantApply`), which is required regardless.
- **CloudWatch:** each finding is one log line, `guardrail_finding {"event": "guardrail_finding", "conversation_id", "source", "policy", "category"}`, with no text.
  - Logs Insights: `filter @message like /guardrail_finding/`.
- **Not yet verified on AWS:** the spec's spike check (detect-mode assessments appear in the trace when every action is `NONE`) and the seam 3 smoke test. Both need the FEX runtime deployed.
