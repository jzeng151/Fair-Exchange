# Spec: Timed clean redeploy and demo run-through (#40)

Status: approved for build, 2026-11-04.

## Problem Statement

The vision document measures deployability with a timed redeploy into a second sandbox account or stack name on day two, with the scripted scenarios running against the fresh stack. A redeploy that only works for the person who built it, or that collides with the main sandbox, proves nothing.

## Solution

On day two, a team member deploys a full second copy under a different stack name in the same sandbox account (decided 2026-11-04). They use only the single command ([#5](05-cdk-stack.md)) and the handoff documents ([#39](39-handoff.md)). The copy is timed, S1 to S6 are run against it ([#35](35-scenarios-and-labels.md)), and it is torn down leaving nothing behind.

## User Stories

1. As an FTUSA reviewer, I want a measured time for a full deploy from scratch, so that deployability is a number, not a claim.
2. As an FTUSA engineer, I want the redeploy done by following only the handoff documents, so that I know they're enough.
3. As a tester, I want the scripted scenarios to pass on the fresh stack, so that the deploy is proven to work, not just to finish.
4. As a team member, I want the second copy unable to touch the main sandbox's data, so that the test is safe to run during the event.
5. As a team member, I want teardown to leave nothing behind, so that the account stays clean and costs stop.

## Implementation Decisions

- **Target.** Stack name `FairExchangeRedeploy` in the sandbox account, `disposable=true` ([#5](05-cdk-stack.md)).
- **Runner.** Someone other than the person who wrote the deploy script, following only `docs/handoff/`.
- **Procedure:**
  1. Start the timer.
  2. Run the single deploy command with the new stack name.
  3. Stop the timer when the script's smoke check passes; the script prints the elapsed time.
  4. Run S1 to S6 against the new stack's API, using the scenario files.
  5. Check each scenario's expected outcome, the Athena join query for S1, and the reviewer view for S1.
  6. Tear down with the destroy command and confirm no resources tagged with the stack name remain.
- **Account prerequisites.** Already met in the sandbox (Transaction Search is on). The handoff documents what a truly clean account needs instead, since this run can't prove it.
- **Record.** The elapsed deploy time, the pass or fail result of each scenario, every handoff gap found, and teardown confirmation. These go in `docs/handoff/` and the #40 issue.
- **Isolation.** The second stack derives every resource name from its own stack name and has its own KMS key, so it can't read or write the main stack's data.

## Testing Decisions

This spec is itself a test. The scenario checks reuse the [#35](35-scenarios-and-labels.md) files; the template test in [#5](05-cdk-stack.md) proves two stacks share no names.

## Out of Scope

- Proving a second AWS account (considered and not chosen on 2026-11-04)

## Further Notes

### Not decided (do not build or assume)

- How the scenarios sign in as their producers. This depends on the sign-in stand-in ([#11](11-identity.md)). Step 4 is blocked until it is decided.
