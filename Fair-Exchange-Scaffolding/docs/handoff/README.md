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
- [ ] API routes
- [ ] CDK outputs and deploy steps (timed clean redeploy, #40)
- [ ] Synthetic data generator and loading instructions
- [ ] Stand-in → target mapping (Athena → Redshift "Atlas", DynamoDB → production store, test identities → Okta)
- [ ] Known limitations
