# Sandbox deployment

Deployed November 3, 2026 from scaffold commit `4f9c590` with the hosting changes
on local branch `chore/deploy-sandbox`. Deployment ran through the workshop
terminal in Firefox. Hosting and CI/CD changes are prepared on that branch for PR review.

| Item | Value |
| --- | --- |
| App | https://d2440kcc3350k5.cloudfront.net |
| AWS account | `100300582834` |
| Region | `us-west-2` |
| CloudFormation stack | `FairExchange` |
| Stack status | `CREATE_COMPLETE` |
| CloudFront distribution | `E20KHI0EJ4NYZI` |
| Website bucket | `fairexchange-webbucket12880f5b-fc6igasbo1p8` |

The app currently displays the repository's Fair Exchange placeholder. The API,
Strands agent, data tools, and review features are stubs and were not deployed.
The website bucket contains only the four compiled web files.

Validation completed locally and in the sandbox: Vue type check and production
build, infrastructure TypeScript check, CDK synthesis, CloudFormation creation,
CloudFront invalidation, and an HTTPS smoke check. The Vue production dependency
audit reported no known vulnerabilities. The build dependencies reported moderate
advisories; they are not installed on the static hosting service.

To redeploy, follow [infra/README.md](../../infra/README.md). The sandbox checkout
is `/workshop/Fair-Exchange/Fair-Exchange-Scaffolding`; its deployment log is
`/tmp/fair-exchange-deploy.log`. The bucket and encryption key are retained on
stack deletion. Full cleanup requires handling those retained resources.

## CI/CD setup status

[PR #48](https://github.com/jzeng151/Fair-Exchange/pull/48) contains the CI/CD
configuration. `Scaffold checks` is required on `main`; the existing one-review
approval rule is preserved. Merge the PR to enable the workflow for future
branches and automatic website deployment after successful checks on `main`.
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
