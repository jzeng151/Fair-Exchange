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
configuration. The [PR checks passed](https://github.com/jzeng151/Fair-Exchange/actions/runs/41733547889).
`Scaffold checks` is required on `main`; the existing one-review approval rule
is preserved. The workflow must be merged to apply to future branches.

The sandbox IAM simulation allows `iam:CreateOpenIDConnectProvider`,
`iam:CreateRole`, `iam:PutRolePolicy`, and `iam:PassRole`. GitHub's OIDC settings
confirm immutable repository subjects. The scoped identity template is prepared,
but role creation is awaiting action-time approval. No AWS credentials are stored
in GitHub, no deployment role has been provisioned, and `AWS_DEPLOY_ROLE_ARN` is
unset, so the publish job is currently skipped. After approval, create the identity,
validate one setup-branch deployment, and remove temporary branch access before
marking the PR ready for review.
