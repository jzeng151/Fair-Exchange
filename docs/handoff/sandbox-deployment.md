# Sandbox deployment

Initially deployed November 3, 2026 from scaffold commit `4f9c590` with the hosting changes
on local branch `chore/deploy-sandbox`. Deployment ran through the workshop
terminal in Firefox. Hosting and CI/CD changes subsequently merged in PR #48.

| Item | Value |
| --- | --- |
| App | https://d2440kcc3350k5.cloudfront.net |
| AWS account | `100300582834` |
| Region | `us-west-2` |
| CloudFormation stack | `FairExchange` |
| Stack status | `UPDATE_COMPLETE` |
| CloudFront distribution | `E20KHI0EJ4NYZI` |
| Website bucket | `fairexchange-webbucket12880f5b-fc6igasbo1p8` |

The initial deployment displayed the Fair Exchange placeholder and uploaded four
compiled web files. Subsequent successful runs on `main` publish the current
website build. Website publishing does not deploy the API, Strands agent, or data services.

Validation completed locally and in the sandbox: Vue type check and production
build, infrastructure TypeScript check, CDK synthesis, CloudFormation creation,
CloudFront invalidation, and an HTTPS smoke check. The Vue production dependency
audit reported no known vulnerabilities. The build dependencies reported moderate
advisories; they are not installed on the static hosting service.

To redeploy, follow [infra/README.md](../../infra/README.md). The sandbox checkout
is `/workshop/Fair-Exchange`; its initial deployment log is
`/tmp/fair-exchange-deploy.log`. The bucket and encryption key are retained on
stack deletion. Full cleanup requires handling those retained resources.

## CI/CD setup status

[PR #48](https://github.com/jzeng151/Fair-Exchange/pull/48) added the CI/CD
configuration. `Scaffold checks` is required on `main`; the existing one-review
approval rule is preserved. Automatic website deployment runs after successful checks on `main`.
Manual workflow runs on `main` can also publish. Pull-request runs have no AWS
access, and deployment jobs are serialized.

The approved `FairExchangeGitHub` CloudFormation stack provisions GitHub OIDC and
`arn:aws:iam::100300582834:role/FairExchangeGitHubDeploy`. The repository variable
`AWS_DEPLOY_ROLE_ARN` points to this role. No long-lived AWS credentials are stored
in GitHub. The role can publish only the existing static website and refresh its
CloudFront cache; infrastructure and IAM updates remain manual.

The [end-to-end GitHub run](https://github.com/jzeng151/Fair-Exchange/actions/runs/41733955004)
passed all checks, authenticated through OIDC, published the compiled files,
waited for cache invalidation, compared the served HTML to the build, and fetched
all built assets successfully. Validation used temporary access for
`chore/deploy-sandbox`. That branch has been removed from the workflow's deploy
triggers and from AWS trust. The role now trusts only the immutable subject
`repo:jzeng151@87108282/Fair-Exchange@1444721780:ref:refs/heads/main`.

The setup checkout in the browser workshop is `/tmp/fair-exchange-cicd`. Identity
setup logs are `/tmp/fair-exchange-oidc.log` and
`/tmp/fair-exchange-oidc-final.log`. These are temporary workshop files; the PR
contains the reproducible setup instructions and configuration.

## Root layout verification

[PR #60](https://github.com/jzeng151/Fair-Exchange/pull/60) moved the application
folders to the repository root and updated workflow working directories, npm cache
paths, and the publishing command to `bash infra/publish-web.sh`. The scripts
already resolve paths relative to `infra/`, so they need no path changes.

The [post-move run for commit `25473c8`](https://github.com/jzeng151/Fair-Exchange/actions/runs/41859375024)
passed both `Scaffold checks` and `Publish sandbox`, including OIDC authentication
and the live HTML and asset checks. The directory move requires no AWS resource
replacement or identity-policy change.

## Application deployment verification, November 4, 2026

[PR #151](https://github.com/jzeng151/Fair-Exchange/pull/151) deploys the missing
producer and reviewer record routes and connects the hosted views to them.
The sandbox API reports version `72cbd1b`. The CloudFormation update completed;
the local CDK watcher stalled afterward, so the operator stopped the watcher and
resumed data loading, publishing and smoke checks. This was not a successful
uninterrupted timed run of the single command.

The deployed application now includes S3/CloudFront hosting, API Gateway and
Lambdas for chat, identity, records, review and analytics, the FEX AgentCore runtime
and Memory, Guardrail, standards Knowledge Base, DynamoDB tables, and the
DynamoDB-to-S3 sync with Glue/Athena queries. Athena sync and analytics queries
remain separate CloudFormation stacks.

Verified against the live deployment:

- API health returns `72cbd1b`; the published HTML and built assets pass the
  hosting smoke check. Firefox shows the live reviewer sign-in page.
- Standards Knowledge Base retrieval passes.
- Producer, reviewer and admin identities resolve; anonymous requests return 401;
  authenticated callers with the wrong role receive 403; responses include CORS.
- A producer sees only their records. Reviewer corrections preserve the original;
  unresolved PII and stale versions block approval or writes; approved records
  are read-only. The reviewer correction appears in the producer projection.
- A synthetic approved record reaches S3 and Athena as version 3. The two
  regression records are deleted from DynamoDB and their S3 copies disappear.
- Analytics returns 200 for both review filters and 401 without credentials.
  The separate seeded series contains 116 reviewed completed records, 172
  completed records including pending, and 28 declined records. All 200 seeded
  objects stay under `records-seeded/`, outside DynamoDB and the reviewer queue.

The deployed routes are `/#/live`, `/#/me`, `/#/review`, and `/#/admin`.
The root producer route remains the scripted demonstration. Credentials stay in
Secrets Manager; see [role-specific access](02-deploy.md) for the stack outputs.

## Remaining work for issue #5

The current sandbox is deployed, but [issue #5](https://github.com/jzeng151/Fair-Exchange/issues/5)
requires a full deployment into a clean account. Its
[approved spec](../specs/05-cdk-stack.md) has additional requirements:

- [ ] Incorporate Athena sync, Glue resources and analytics queries into the
  documented single-command dependency sequence. The current script only enables
  analytics and seeded loading when the separate Athena sync stack already exists.
- [ ] Implement the stack-name, disposable-copy and eval-access parameters across
  resources and scripts, with the guarded destroy command and retained-resource
  handling required by the spec. Retire obsolete spike deployment commands.
- [ ] Make clean-account prerequisites reproducible: model access, CloudTrail,
  Transaction Search setup and readiness checks. The sandbox's existing setup
  alone does not prove a clean-account deployment.
- [ ] Complete the spec's template invariant tests and verify encryption,
  least-privilege roles, named operator log-read access, and observability/content
  capture behavior in the disposable copy.
- [ ] Run the complete single command in a clean account or the approved isolated
  validation environment; record elapsed time, outputs, end-to-end results,
  repeat deployment behavior and cleanup evidence for #39 and #40.

Automatic deployment of infrastructure from GitHub is a separate capability from
the issue's single-command requirement. The current OIDC role permits website
publishing only; broader CI deployment needs a separately scoped role.
