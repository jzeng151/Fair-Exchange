# infra/

AWS CDK v2 (TypeScript). Issue #5 requires a single-command full-stack deployment;
issue #40 records a timed clean redeploy. `infra/deploy.sh` builds and deploys the application,
including the agent runtime, website, chat, producer-record and reviewer APIs, and analytics
when the Athena sync stack exists.

The `FairExchange` stack hosts the Vue website using a private KMS-encrypted S3 bucket
and CloudFront with origin access control. AgentCore hosts FEX; API Gateway and Lambda
serve the application API. Only compiled files from `web/dist` are published to the website bucket.

Run from the repository root:

```bash
npm --prefix infra ci
(cd infra && npx cdk synth FairExchange) # preview only; creates nothing
EXPECTED_AWS_ACCOUNT=100300582834 AWS_REGION=us-west-2 \
  FEX_MAX_LIFETIME_MINUTES=1440 LOG_RETENTION_DAYS=30 bash infra/deploy.sh
```

`web/`, `api/`, `agent/`, `data/`, `eval/`, and `infra/` are root-level folders.
The scripts resolve their paths from their own location, so they also work when
called from another directory. Moving the source tree does not change the stack
name, resource IDs, GitHub OIDC trust, or website URL. See the
[remaining work for #5](../docs/handoff/sandbox-deployment.md#remaining-work-for-issue-5).

The script builds and checks the app, deploys the stacks with the caller's existing credentials, uploads the
site, invalidates CloudFront, and checks the HTTPS response. See "Stacks and the deploy order" below for the
CDK bootstrap and the stack layout. Commit both package lockfiles for repeatable builds.

Stack outputs are `WebUrl`, `WebBucketName`, and `WebDistributionId`. The bucket
policy grants object reads only to this distribution. CDK's KMS decrypt grant is
restricted to CloudFront distributions in this account to avoid a dependency cycle.

The bucket and KMS key are retained if the stack is deleted, so stack deletion
alone does not remove uploaded objects or all billable resources. CloudFront,
S3, and KMS usage is billed to the sandbox.

## GitHub Actions

The `CI` workflow runs the existing Python tests, API and web type checks, web
build, and CDK synthesis on every pull request. Actions are pinned by commit SHA.
The `Scaffold checks` status is intended to be required before merging to `main`.

After checks pass on a push or manual run on `main`, `Publish sandbox` uses GitHub OIDC to assume
`FairExchangeGitHubDeploy`, builds the website, runs `publish-web.sh`, and verifies
the served HTML and asset responses. Set the repository variable
`AWS_DEPLOY_ROLE_ARN` to the role ARN. No AWS access keys are stored in GitHub.
Remove that variable to disable automated publishing.

The deployment role can publish only this website's files, use its encryption key
through S3, read the hosting stack outputs, and create/read CloudFront invalidations.
It cannot change infrastructure, IAM, the agent, or application records. Deploy
infrastructure changes separately with `deploy.sh` using sandbox credentials.

Provision the OIDC identity once with:

```bash
EXPECTED_AWS_ACCOUNT=100300582834 bash infra/configure-github-oidc.sh
```

This creates the separate `FairExchangeGitHub` stack and requires IAM permissions.
Its trust policy uses this repository's verified immutable OIDC subject IDs, not a
wildcard repository name. The role trusts only `main`. The setup script's optional
`VALIDATION_BRANCH=chore/deploy-sandbox` parameter exists solely for initial
validation; omit it during routine setup and updates. Pull-request runs have no
AWS access, and deployment jobs are serialized to prevent overlapping uploads.

CI and manual deployment instructions remain usable after the workshop ends;
automated publishing needs a live sandbox account and its AWS resources.


## Stacks and the deploy order (#5)

`FairExchange` uses CDK's standard synthesizer (docs/specs/05-cdk-stack.md), so its Lambdas and custom resources
can be CDK assets; `deploy.sh` bootstraps the account if needed (the `CDKToolkit` stack). Files the stack reads
while it is created, like the clause documents, are uploaded by `deploy.sh` into a small stack deployed first:

| Stack | Holds | Deleted with the stack? |
|---|---|---|
| `FairExchangeArtifacts` | The artifacts key (customer-managed KMS, rotated) and the artifacts bucket (encrypted with it): standards clause documents under `clauses/`, later the agent code zip | No. Both are kept. Clause documents expire after 30 days (`STANDARDS_DOCS_TTL_DAYS`), so a kept bucket empties itself. The key costs about $1 a month until it is scheduled for deletion. |
| `FairExchange` | Website hosting (with its own `WebKey`), the application data key, the Guardrail, the standards Knowledge Base (vectors encrypted with the data key) and its ingestion, AgentCore Memory (encrypted with the data key), the records and conversations tables (data key, point-in-time recovery), and later the API, agent runtime, records and analytics | The Knowledge Base, its vectors and ingestion resources are deleted. The website bucket, `WebKey`, the data key and both tables are kept. |

`deploy.sh` runs, in order:

1. Checks CDK bootstrap and runs `cdk bootstrap` if the account isn't bootstrapped.
2. Builds the website.
3. Builds one document per APS/FPS clause (`python -m fx_data.standards_kb`), each with a `.metadata.json`
   sidecar holding `clause_id` and `standard`, and computes their content hash.
4. Type-checks the infrastructure code.
5. Deploys `FairExchangeArtifacts`.
6. Uploads the clause documents with `aws s3 sync --delete`. Every deploy re-uploads all of them, which
   resets their expiry and restores any that expired.
7. Deploys `FairExchange` with `cdk deploy`, passing the artifacts bucket, its key and the hash as CDK context. The Knowledge Base uses an S3 Vectors
   store encrypted with the data key, Titan Text Embeddings V2 and no chunking. A custom resource starts an
   ingestion job and a Step Functions loop polls it: ingestion failure, any failed document, or more than
   20 minutes fails the deploy, and CloudFormation rolls back only the new resources. The hash is a custom
   resource property, so changed clauses re-ingest and unchanged ones do not.
- Uploads the producer data to the data bucket (after `FairExchange` is deployed): `python -m fx_data.export`
  writes one JSON-lines file per table (producers, certification, Premium projects, survey summary facts, the
  peer catalog) and `aws s3 sync --delete` uploads them. Glue tables in the `<stack>_source` database
  (`DataGlueDatabase` output) read them for Athena. Only allowlisted data is exported; raw survey answers never are.
8. Publishes the website (`publish-web.sh`) and runs the Knowledge Base smoke test
   (`eval/tests/test_standards_kb_smoke.py`). It prints `StandardsKnowledgeBaseId` for `FEX_STANDARDS_KB_ID`.

`deploy-web.sh` now just runs `deploy.sh`. Do not deploy `cdk.out/FairExchange.template.json` by hand
without the context `deploy.sh` passes: the Knowledge Base would point at a placeholder bucket.

**Account prerequisites:** credentials that can create IAM roles, KMS keys, Bedrock Knowledge Bases and S3
Vectors (the GitHub deploy role cannot), and access to Amazon Titan Text Embeddings V2 in the region. The first run
bootstraps CDK with its default settings: the `CDKToolkit` stack holds an asset bucket, an ECR repository and the
roles `cdk deploy` uses; its CloudFormation execution role has `AdministratorAccess`, as is CDK's default.

**Expiry caveat:** clause documents expire 30 days after the last deploy. Only ingest by deploying (the
script uploads first). A sync started by hand in the console after they expired would empty the Knowledge
Base; re-run `deploy.sh` to restore it.

The ingestion handler is inline Lambda code (`lib/standards-kb/ingest_handler.py`, under 4 KB) because
no CDK assets can be published.

## Tables (#25, #26)

`FairExchange` outputs `RecordsTableName`, `RecordsTableArn`, `RecordsTableStreamArn`, `ConversationsTableName` and
`ConversationsTableArn`. The records table has a keys-only stream for the Athena sync (#28). To deploy the sync stack
against it until it is part of `deploy.sh`:

```bash
out() { aws cloudformation describe-stacks --stack-name FairExchange --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text; }
EXPECTED_AWS_ACCOUNT=100300582834 RECORDS_TABLE_NAME="$(out RecordsTableName)" \
  RECORDS_TABLE_STREAM_ARN="$(out RecordsTableStreamArn)" RECORDS_TABLE_KEY_ARN="$(out DataKeyArn)" \
  bash infra/deploy-athena-sync.sh
```

## Agent runtime (#5, #13)

`deploy.sh` packages the agent (`agent/` and `data/` wheels plus the locked dependencies, ARM64 Linux wheels, and
`agent/runtime/fex/main.py` as the entry point), uploads it to the artifacts bucket under `agent/fex-<hash>.zip`,
and deploys `FairExchange` with the runtime (`AgentRuntimeArn`, `AgentRuntimeId`, `AgentRuntimeLogGroup` outputs).
Two values are required, with no defaults (the specs leave them to whoever deploys):

```bash
EXPECTED_AWS_ACCOUNT=100300582834 AWS_REGION=us-west-2 \
  FEX_MAX_LIFETIME_MINUTES=1440 LOG_RETENTION_DAYS=30 bash infra/deploy.sh   # the sandbox's current values
```

- **Role:** the #13 spec's "Agent runtime permissions" (`lib/agent-runtime.ts`): the two US model profiles, the
  Guardrail, `bedrock:Retrieve` on the standards Knowledge Base, `GetItem`/`PutItem` on the records table, the
  memory resource, Comprehend PII detection, its code object, its log group, X-Ray and metrics.
- **Logs:** the stack creates the runtime log group (data key, `LOG_RETENTION_DAYS`) and its `otel-rt-logs`
  stream. The role cannot create log groups, so nothing is written without retention. The CloudWatch OTLP logs
  endpoint needs the stream to exist; without it every export fails with 400.
- **No message content in logs:** `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` (the Bedrock call) and
  `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_unredacted_attributes=` (the Strands tracer: every content attribute becomes
  `[REDACTED]`). Verified in the sandbox on 2026-11-04: a marker sentence and the producer's words appeared in no
  event of the runtime log group or `aws/spans`. Re-check after changing the agent or its OpenTelemetry versions.
- **Transaction Search** must be on (ADR 0002); `deploy.sh` stops with instructions if it isn't.
- **Try it** without the API: `cd agent && uv run python ../scripts/e2e/runtime_conversation.py --runtime-arn <AgentRuntimeArn>`
  runs one scripted conversation with real models (a few cents) and saves a record (`record_id` = the printed
  conversation ID).
