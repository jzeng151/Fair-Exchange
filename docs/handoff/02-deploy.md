# Deploy

The deploy lives in `infra/` (AWS CDK v2, TypeScript). The single command is `infra/deploy.sh` (#5); issue #40
records a timed clean redeploy with it. The full stack is assembled in the CDK app as each feature's resources
land: [`infra/README.md`](../../infra/README.md#stacks-and-the-deploy-order-5) lists what each stack holds today
and is the authoritative, step-by-step source; this page is the handoff summary.

## Prerequisites (clean account)

- An AWS account and credentials that can create IAM roles, KMS keys, Bedrock Knowledge Bases and S3 Vectors
  (and the rest of the stack's resources). `deploy.sh` bootstraps CDK in the account if needed.
- Region `us-west-2` (the US inference profiles and the sandbox are US-region; ADR 0001).
- **Amazon Bedrock model access** enabled for the configured Claude inference profiles (the small and
  large models, [#13](../specs/13-conversation-steps.md)) and for **Amazon Titan Text Embeddings V2** (the
  standards Knowledge Base, [#17](../specs/17-standards-grounding.md)).
- **CloudTrail / Transaction Search** enabled in the target account for AgentCore Observability
  (see [ADR 0002](../adr/0002-agentcore-runtime-spike.md); verified by #5/#40 in a clean account).
- Node.js 22 and the AWS CLI; Python 3.12 and `uv` for the agent and data packages. The CDK toolkit comes
  from `infra/`'s own dependencies (`npx cdk`).

## The command

Run from the repository root (see `infra/README.md` for the current scope and the account guard):

```bash
npm --prefix infra ci
(cd infra && npx cdk synth FairExchange)   # preview only; creates nothing
EXPECTED_AWS_ACCOUNT=<account> AWS_REGION=us-west-2 \
  FEX_MAX_LIFETIME_MINUTES=1440 LOG_RETENTION_DAYS=30 bash infra/deploy.sh
```

The script refuses to run if the credentials belong to a different account, then builds artifacts,
deploys infrastructure, uploads source data, and publishes the website with smoke tests
([details](../../infra/README.md#stacks-and-the-deploy-order-5)). `infra/deploy-web.sh` is kept for older
instructions and just runs `deploy.sh`. Record the elapsed time here from the #40 run.

**Not yet possible (needed by #40):** deploying a second copy under another stack name. The
[#5 spec](../specs/05-cdk-stack.md) makes the stack name and a `disposable` flag parameters; until they land,
`deploy.sh` always deploys the `FairExchange` stack, so running it for #40 would update the main sandbox.

## Configuration values

The stack provides these to the application; each is a value FTUSA sets for their account.

| Value | Set on | Meaning | Spec |
|---|---|---|---|
| `CONVERSATIONS_TABLE` | chat + sweep Lambdas | DynamoDB table of conversations | [#25](../specs/25-chat-endpoint.md) |
| `AGENT_RUNTIME_ARN` | chat + sweep Lambdas | the AgentCore Runtime to invoke | [#25](../specs/25-chat-endpoint.md) |
| `ALLOWED_ORIGIN` | chat + health Lambdas | the website's origin, the only CORS origin (`WebUrl`) | [#25](../specs/25-chat-endpoint.md) |
| `DEMO_PASSCODE_SECRET_ARN`, `DEMO_PRODUCER_IDS` | authorizer Lambda | the sign-in stand-in: the passcode secret and the scenario producer allow-list (from `eval/scenarios/`) | [#11](../specs/11-identity.md) |
| `DEMO_ROLE=admin`, `DEMO_PASSCODE_SECRET_ARN` | admin authorizer Lambda | the admin passcode stand-in for analytics | [#11](../specs/11-identity.md) |
| `ATHENA_WORKGROUP`, `ANALYTICS_NAMED_QUERY_IDS` | analytics Lambda | the `fex` workgroup and the `AnalyticsNamedQueryIds` output; `deploy.sh` adds the route only when `FairExchangeAthenaSync` exists | [#29](../specs/29-analytics-api.md) |
| `INACTIVITY_MINUTES` | sweep Lambda | idle period before a conversation is auto-closed: 120 (decided 2026-11-04, [#13](../specs/13-conversation-steps.md)) | [#25](../specs/25-chat-endpoint.md) |
| `RECORDS_TABLE` | write-back, review, "your record" Lambdas | DynamoDB records table | [#26](../specs/26-write-back.md) |
| `FEX_SMALL_MODEL`, `FEX_LARGE_MODEL` | agent runtime | the Claude inference profiles (default to `us.` profiles) | [#13](../specs/13-conversation-steps.md) |
| `FEX_RECORDS_TABLE` | agent runtime | records table the agent writes | [#26](../specs/26-write-back.md) |
| `FEX_GUARDRAIL_ID`, `FEX_GUARDRAIL_VERSION` | agent runtime | the detect-mode Guardrail (`guardrail.runtimeEnvironment`) | [#12](../specs/12-guardrail.md) |
| `FEX_STANDARDS_KB_ID` | agent runtime | the standards Knowledge Base (the `StandardsKnowledgeBaseId` output). Required for a non-demo runtime: without it the standards retrieval is unconfigured and the grounded-answer turn fails | [#17](../specs/17-standards-grounding.md) |
| `FEX_MEMORY_ID` | agent runtime | the AgentCore Memory resource (resume + long-term memory) | [memory](../specs/memory.md) |
| `FEX_EVENT_EXPIRY_DAYS`, `FEX_MAX_LIFETIME_MINUTES` | agent runtime | memory retention (7 days) and the maximum conversation lifetime (1,440 minutes, decided 2026-11-04); event expiry must exceed the lifetime. `deploy.sh` takes the lifetime as `FEX_MAX_LIFETIME_MINUTES` | [memory](../specs/memory.md) |
| `LOG_RETENTION_DAYS` | `deploy.sh` input | log retention for the agent runtime and the chat API's Lambdas; required, no default. The sandbox uses 30 (see [FTUSA decisions](06-known-limitations.md#decisions-for-ftusa)) | [#5](../specs/05-cdk-stack.md) |
| `SYNC_BUCKET` (with `RECORDS_TABLE`) | the manual resync command (`python -m fex_sync.resync`, [sync/README](../../sync/README.md)) | the records bucket to rebuild from the table | [#28](../specs/28-athena-sync.md) |

**Never set `FEX_DEMO_MODELS` on a deployed runtime.** It replaces Claude with the scripted demo model used for
local runs and CI (`scripts/e2e/run_local.sh`). Local-only settings (`FEX_DEMO_MODELS`, `FEX_LOCAL_RECORDS_DIR`,
`FEX_AGENT_URL`, `FEX_API_PORT`) are described in the [README](../../README.md#run-the-whole-chain-locally-no-aws).

## Stack outputs

The `FairExchange` stack emits (see `infra/lib/`): `WebUrl`, `WebBucketName`, `WebDistributionId` (hosting);
`GuardrailId`, `GuardrailVersion` ([#12](../specs/12-guardrail.md)); `StandardsKnowledgeBaseId`,
`StandardsKnowledgeBaseArn` ([#17](../specs/17-standards-grounding.md); the runtime reads the ID as
`FEX_STANDARDS_KB_ID`); `MemoryId`, `MemoryArn` ([memory](../specs/memory.md)); `AgentRuntimeArn`,
`AgentRuntimeId`, `AgentRuntimeLogGroup` (the agent); `ApiUrl` (the chat API, [#25](../specs/25-chat-endpoint.md))
and `DemoPasscodeSecretArn` (the demo passcode, [#11](../specs/11-identity.md); read it with
`aws secretsmanager get-secret-value --secret-id <arn> --query SecretString --output text`); with analytics
on, `AdminPasscodeSecretArn` (the admin passcode, read the same way). The Athena sync (`SyncFunctionName`, `RecordsBucketName`,
`AthenaWorkGroup`; deployed with `infra/deploy-athena-sync.sh`, [#28](../specs/28-athena-sync.md)) and the
analytics queries (`AnalyticsNamedQueryIds`, [#29](../specs/29-analytics-api.md)) are separate stacks. The Athena
sync stack also emits `AthenaResultsBucketName` and `SyncKeyArn`. When it exists, `deploy.sh` deploys the
analytics queries stack and adds `GET /analytics` to the chat API.

## Teardown

Some resources are **retained** when the stack is deleted (the website bucket and its key, the data key and
both tables; [table](../../infra/README.md#stacks-and-the-deploy-order-5)), so deleting the stack does not remove
every billable resource. The [#5 spec](../specs/05-cdk-stack.md) adds a destroy script for disposable copies;
it doesn't exist yet. Only the Athena sync has one (`infra/destroy-athena-sync.sh`). Record the exact teardown
steps for the full stack here once #5 lands and #40 exercises them.

## CI/CD and sandbox state

The current sandbox deployment, the GitHub OIDC publishing role, and the full-stack deployment
checklist for #5 are in [sandbox deployment](sandbox-deployment.md).

## Analytics deployment smoke check

When the Athena sync stack exists, `infra/deploy.sh` also runs
`scripts/e2e/analytics_smoke.py` before reporting success. It checks that
anonymous analytics access returns 401 and that both authenticated views return
200 with JSON. This exercises all four named Athena queries, including the live
and seeded AI-usage aggregations. The script reads the admin passcode from Secrets
Manager in memory and never prints it. The deployment caller needs read access to
that existing secret. The GitHub website-only publishing role is unchanged.

Run the check separately with Python 3 and the AWS CLI:

```bash
python3 scripts/e2e/analytics_smoke.py --api <ApiUrl> --admin-secret-arn <AdminPasscodeSecretArn>
```

Athena exposes each `ai_usage` array element as one struct. The footprint queries
alias that struct as `u` and select `u.model_id`, `u.input_tokens`, and
`u.output_tokens`. Assigning three aliases to the one element fails with
`MISMATCHED_COLUMN_ALIASES` and makes the analytics endpoint return 503.

## Live reviewer and producer records

The application stack deploys `GET /me`, `GET /me/records`, `GET /records`,
`GET/PATCH /records/{id}`, and `POST /records/{id}/approve`. Each handler uses the
authorizer's identity and its own Lambda role. Producer reads can scan only the
records table. Review reads use Scan/GetItem; corrections and approval use GetItem/PutItem.
No record handler can delete records or invoke the agent.

The sandbox has three separate credentials, generated in Secrets Manager with KMS encryption:

| Role | Stack output | Request headers |
| --- | --- | --- |
| Producer | `DemoPasscodeSecretArn` | `x-demo-passcode` plus an allow-listed `x-demo-producer-id` |
| Reviewer | `ReviewerPasscodeSecretArn` | `x-demo-reviewer-passcode` |
| Admin | `AdminPasscodeSecretArn` | `x-demo-admin-passcode` |

Retrieve the appropriate passcode with `aws secretsmanager get-secret-value --secret-id <output ARN>`
using the existing operator credentials. Do not put passcodes in source, a build variable,
or browser storage. The live views keep them only in component memory. Production identity
remains the separate FTUSA integration described in the identity spec.

`GET /me` accepts any one of these credentials and returns the user ID and roles.
The new record routes reject authenticated callers with the wrong role with 403.
Supplying multiple role credentials is rejected. The shared identity authorizer has
caching disabled because its credential headers are alternatives; no cached policy
can cross roles. Existing chat and analytics authorizers retain their scope.

With `VITE_FEX_API_URL` set, the website's Your record and Fair Trade USA views use
these APIs. The reviewer can filter, inspect, correct, resolve PII flags and approve
closed records. Stale edits show a reload action without discarding the draft;
approved records are read-only. Without an API URL, browser-only demos still work.

When the Athena sync stack exists, deployment also validates and uploads the 200
deterministic synthetic analytics records using `agent/scripts/load_seeded_records.py`.
The loader replaces only the `records-seeded/` prefix in the records bucket. It
does not write to DynamoDB, the live `records/` prefix, or the reviewer queue.

The deployment runs `scripts/e2e/records_smoke.py` from the agent environment when
the Athena sync stack exists. It verifies identity and role separation, producer
scope, CORS, PII gating, reviewer corrections, version conflicts, approval, and the
reviewed record in S3/Athena. It creates two synthetic records and deletes only
those records in a cleanup block. Logs, PITR history and Athena query outputs remain
subject to their configured retention.
