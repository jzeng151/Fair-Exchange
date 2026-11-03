# infra/

AWS CDK v2 (TypeScript). One stack, one command. The Vision doc requires a timed clean redeploy into a fresh account (issue #40).

```bash
npm install
npx cdk synth            # preview only; creates nothing
npx cdk deploy --all     # deploys to the account in your AWS profile
npx cdk destroy --all    # removes everything
```

First time in an account: `npx cdk bootstrap`.
