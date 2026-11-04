# Deploy

The deploy lives in `infra/` (AWS CDK v2, TypeScript). The single-command full-stack deploy is
issue #5; issue #40 records a timed clean
redeploy. Until #5 lands, the shipped command deploys **website hosting only** — the full stack is
assembled in the CDK app as each feature's resources land. The authoritative, step-by-step instructions
are [`infra/README.md`](../../infra/README.md); this page is the handoff summary.

## Prerequisites (clean account)

- An AWS account and credentials with permission to create the stack's resources.
- Region `us-west-2` (the US inference profiles and the sandbox are US-region; ADR 0001).
- **Amazon Bedrock model access** enabled for the configured Claude inference profiles (the small and
  large models, [#13](../specs/13-conversation-steps.md)).
- **CloudTrail / Transaction Search** enabled in the target account for AgentCore Observability
  (see [ADR 0002](../adr/0002-agentcore-runtime-spike.md); verified by #5/#40 in a clean account).
- Node.js and the AWS CDK toolkit; Python 3.12 and `uv` for the agent and data packages.

## The command

Run from the repository root (see `infra/README.md` for the current scope and the account guard):

```bash
npm --prefix infra ci
(cd infra && npx cdk synth FairExchange)   # preview only; creates nothing
EXPECTED_AWS_ACCOUNT=<account> AWS_REGION=us-west-2 bash infra/deploy-web.sh
```

The script verifies the account ID before creating anything, builds and checks the app, deploys the
synthesized template with the caller's credentials, uploads `web/dist`, invalidates CloudFront, and
checks the HTTPS response. As the full stack lands (#5), one documented command will build, provision,
load required data and publish in dependency order; record its elapsed time here from the #40 run.

## Configuration values

The stack provides these to the application; each is a value FTUSA sets for their account.

| Value | Set on | Meaning | Spec |
|---|---|---|---|
| `CONVERSATIONS_TABLE` | chat + sweep Lambdas | DynamoDB table of conversations | [#25](../specs/25-chat-endpoint.md) |
| `AGENT_RUNTIME_ARN` | chat + sweep Lambdas | the AgentCore Runtime to invoke | [#25](../specs/25-chat-endpoint.md) |
| `INACTIVITY_MINUTES` | sweep Lambda | idle period before a conversation is auto-closed (value "Not decided", [#13](../specs/13-conversation-steps.md)) | [#25](../specs/25-chat-endpoint.md) |
| `RECORDS_TABLE` | write-back, review, "your record" Lambdas | DynamoDB records table | [#26](../specs/26-write-back.md) |
| `FEX_SMALL_MODEL`, `FEX_LARGE_MODEL` | agent runtime | the Claude inference profiles (default to `us.` profiles) | [#13](../specs/13-conversation-steps.md) |
| `FEX_RECORDS_TABLE` | agent runtime | records table the agent writes | [#26](../specs/26-write-back.md) |
| `FEX_GUARDRAIL_ID`, `FEX_GUARDRAIL_VERSION` | agent runtime | the detect-mode Guardrail (`guardrail.runtimeEnvironment`) | [#12](../specs/12-guardrail.md) |
| `FEX_STANDARDS_KB_ID` | agent runtime | the standards Knowledge Base (the `StandardsKnowledgeBaseId` output). Required for a non-demo runtime: without it the standards retrieval is unconfigured and the grounded-answer turn fails | [#17](../specs/17-standards-grounding.md) |
| `FEX_MEMORY_ID` | agent runtime | the AgentCore Memory resource (resume + long-term memory) | [memory](../specs/memory.md) |
| `FEX_EVENT_EXPIRY_DAYS`, `FEX_MAX_LIFETIME_MINUTES` | agent runtime | memory retention; event expiry must exceed the max conversation lifetime | [memory](../specs/memory.md) |

## Stack outputs

The CDK app emits (see `infra/lib/`): `WebUrl`, `WebBucketName`, `WebDistributionId` (hosting);
`GuardrailId`, `GuardrailVersion` ([#12](../specs/12-guardrail.md)); `StandardsKnowledgeBaseId`,
`StandardsKnowledgeBaseArn` ([#17](../specs/17-standards-grounding.md); the runtime reads the ID as
`FEX_STANDARDS_KB_ID`); `MemoryId`, `MemoryArn` ([memory](../specs/memory.md)); and, as each slice
lands, the records table, agent runtime ARN and role, and the analytics/Athena resources
([#28](../specs/28-athena-sync.md)).

## Teardown

The website bucket and its KMS key are **retained** on stack deletion, so deleting the stack does not
remove uploaded objects or every billable resource. Full cleanup means emptying and removing the
retained bucket and scheduling the key for deletion. Record the exact teardown steps for the full
stack here once #5 lands and #40 exercises them.

## CI/CD and sandbox state

The current sandbox deployment, the GitHub OIDC publishing role, and the full-stack deployment
checklist for #5 are in [sandbox deployment](sandbox-deployment.md).
