# infra/

AWS CDK v2 (TypeScript). Issue #5 requires a single-command full-stack deployment;
issue #40 records a timed clean redeploy. The current command deploys website hosting only.

The `FairExchange` stack hosts the Vue website using a private KMS-encrypted S3 bucket
and CloudFront with origin access control. It does not provision the stub API or
agent. Only compiled files from `web/dist` are published.

Run from the repository root:

```bash
npm --prefix infra ci
(cd infra && npx cdk synth FairExchange) # preview only; creates nothing
EXPECTED_AWS_ACCOUNT=100300582834 AWS_REGION=us-west-2 bash infra/deploy-web.sh
```

`web/`, `api/`, `agent/`, `data/`, `eval/`, and `infra/` are root-level folders.
The scripts resolve their paths from their own location, so they also work when
called from another directory. Moving the source tree does not change the stack
name, resource IDs, GitHub OIDC trust, or website URL. See the
[remaining work for #5](../docs/handoff/sandbox-deployment.md#remaining-work-for-issue-5).

The script builds and checks the app, deploys the synthesized CloudFormation
template with the caller's existing credentials, uploads the site, invalidates
CloudFront, and checks the HTTPS response. No CDK bootstrap or new IAM roles are
needed for this static hosting stack. Commit both package lockfiles for repeatable
builds. Revisit the synthesizer when Lambda or container assets are added.

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
infrastructure changes separately with `deploy-web.sh` using sandbox credentials.

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
