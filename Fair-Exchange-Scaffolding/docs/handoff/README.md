# Handoff package

What Fair Trade USA engineering needs to redeploy and run Fair Exchange in their own account (issue #39):

- [ ] Record schema (generated from `agent/src/fex/models.py`)
- [ ] Tool interface contracts (inputs, outputs, scope rule)
- [ ] API routes
- [ ] CDK outputs and deploy steps (timed clean redeploy, #40)
- [ ] Synthetic data generator and loading instructions
- [ ] Stand-in → target mapping (Athena → Redshift "Atlas", DynamoDB → production store, test identities → Okta)
- [ ] Known limitations
