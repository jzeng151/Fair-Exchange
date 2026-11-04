# Handoff package

## Sandbox scaffold deployment

The hosting slice for issues #5 and #30 deploys the existing Vue placeholder.
Follow [the deployment instructions](../../infra/README.md). The API, AgentCore,
data loaders, and review flows remain unimplemented and are not deployed.

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
Deploy inputs the stack must provide: the conversations table and index, `AGENT_RUNTIME_ARN`, the REST API with response streaming and a 5 minute timeout on the three POST routes, the 15 minute schedule for the sweep, and `INACTIVITY_MINUTES`. Only the chat handlers and the sweep may write the table or invoke the runtime. Until the stack is wired, these handlers are not deployed.
