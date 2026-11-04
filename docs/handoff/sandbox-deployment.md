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
| Stack status | `CREATE_COMPLETE` |
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

## Remaining work for issue #5

[Issue #5](https://github.com/jzeng151/Fair-Exchange/issues/5) requires the full stack
to deploy into a clean account from the CDK project with one command. Static
website publishing satisfies only the hosting portion. As of November 4, 2026:

- [x] Root-level paths work in CI and in the live website deployment.
- [x] Website hosting uses KMS encryption and a scoped GitHub OIDC publishing role.
- [x] Dependency #4 is closed. [PR #56](https://github.com/jzeng151/Fair-Exchange/pull/56)
  demonstrated CDK deployment, invocation, scoped tool context, and AgentCore traces.
  Its spike resources were removed after validation.
- [ ] Integrate the real FEX runtime into the application deployment, replacing
  the separate hello-world spike. Include reproducible ARM64 dependency packaging,
  artifact upload, runtime configuration, and outputs consumed by the API.
- [ ] Add the resources needed by the MVP features as they land: authenticated API
  routes and Lambdas, records storage, data/query resources and loading, guardrails (defined: `FexGuardrail`, #12; wire it to the FEX runtime),
  and frontend configuration. Package the chosen retrieval implementation; managed
  Knowledge Bases are not required if the approved embedded approach is retained.
- [ ] Provide one documented command that builds, provisions, loads required data,
  and publishes the full application in dependency order. `infra/deploy.sh` now does this
  for hosting, the Guardrail and the standards Knowledge Base (#17), using a `FairExchangeArtifacts`
  stack for files the main stack reads. It bootstraps CDK if needed (spec 05: standard synthesizer
  for the application stack). The AgentCore spike and Athena sync still have their own commands. Document account
  prerequisites and avoid dependencies on existing sandbox resource IDs.
- [ ] Apply KMS encryption and least-privilege service roles to the added resources.
  The spike code bucket uses S3-managed encryption and must change for this baseline.
  Verify that only the authenticated API can invoke the application runtime.
- [ ] Verify CloudTrail is enabled in the target account and make its setup or
  preflight check reproducible for a clean-account deployment.
- [ ] Enable and verify AgentCore Observability and CloudWatch logging in the
  integrated runtime. Define log retention and reader permissions in CDK. Resolve
  the content-capture policy with #38 and verify it with a test conversation:
  the spike found full prompts, responses, and tool results in runtime logs with
  no expiry. See ADR 0002 in PR #56 for the evidence.
- [ ] Run the single command in a clean account, record elapsed time and outputs,
  and verify the deployed application end to end. Record update/redeploy behavior,
  prerequisites, and cleanup of retained resources in the handoff for #39 and #40.

Automatic deployment of infrastructure from GitHub is a separate capability from
the issue's single-command requirement. The current OIDC role deliberately permits
website publishing only; any broader CI deployment needs a separately scoped role.
