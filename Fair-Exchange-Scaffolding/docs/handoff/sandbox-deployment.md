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
