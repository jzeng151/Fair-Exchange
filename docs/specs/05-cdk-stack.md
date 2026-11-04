# Spec: CDK stack and single-command deploy (#5)

Status: approved for build, 2026-11-04.

## Problem Statement

The vision document measures deployability by one thing: the full stack deploys into a clean account from the CDK project in a single command. Today the stack holds only web hosting, and the AgentCore spike lives in a separate stack and script set. Every other spec adds resources. Without one agreed stack shape, these problems follow:
- resources get hard-coded names, so a second copy can't be deployed (#40);
- log groups keep producer words forever (ADR 0002);
- a clean account fails on steps CDK doesn't perform.

## Solution

One CDK app deploys everything through one script. The script does three things:
1. Checks the account and its one-time prerequisites.
2. Builds and uploads the agent code.
3. Deploys an artifacts stack and the application stack.

The stack name is a parameter, and every resource name derives from it, so copies never clash. Stateful resources keep their data unless the deployer opts into a disposable copy.

## User Stories

1. As an FTUSA engineer, I want to deploy the whole system into a clean account with one command, so that redeploying in our own account is routine.
2. As a hackathon tester, I want to deploy a second copy under another stack name, so that the timed redeploy (#40) and evals don't touch the main sandbox.
3. As an FTUSA engineer, I want every account-level prerequisite either done by the script or checked with a clear message, so that a clean account doesn't fail halfway.
4. As an FTUSA engineer, I want all data encrypted with KMS and every role scoped to what it needs, so that the sandbox matches the security baseline.
5. As an FTUSA engineer, I want log retention set explicitly on every log group, so that producer words aren't kept forever by default.
6. As an FTUSA engineer, I want stack outputs for every URL and ID the other specs need, so that scripts and docs don't hard-code values.
7. As a team member, I want template tests that fail when an invariant breaks, so that a careless change can't remove encryption or widen a role.

## Implementation Decisions

### Shape

- **Two stacks, one script.**
  - An artifacts stack holds the bucket for agent code zips.
  - The application stack holds everything else.
  - The deploy script deploys both in order. This follows ADR 0002: code zip from S3, bootstrapless synthesizer, a new S3 key per build.
- **Stack name is a parameter** (CDK context `stackName`, default `FairExchange`). No resource sets a physical name. Where a name is required, it is derived from the stack name.
- **Removal policy is a parameter** (context `disposable`, default `false`).
  - When `false`, buckets, tables, the KMS key and the Knowledge Base are retained on stack deletion.
  - When `true`, everything is destroyed, buckets are emptied, and nothing is left behind (#40).
- **The spike stack and scripts are retired** once the runtime is in the application stack.

### Contents of the application stack

Each line names the spec that defines the resource.

- **Security:**
  - one customer-managed KMS key with rotation, used by every bucket, table, log group and the memory resource;
  - a CloudTrail trail (technical environment baseline).
- **Web:** the existing S3 and CloudFront hosting (#30).
- **Data:**
  - the data bucket (producer table, peer catalog, [#14](14-producer-record-tool.md), [#16](16-peer-example-tool.md));
  - the records bucket (live and seeded prefixes, [#28](28-athena-sync.md), [#37](37-seeded-records.md));
  - the stream-failure bucket ([#28](28-athena-sync.md));
  - the Glue database and tables, the Athena workgroup and named queries ([#28](28-athena-sync.md), [#29](29-analytics-api.md)).
- **Records:** the records table with streams, and the conversations table with its producer index ([#26](26-write-back.md), [#25](25-chat-endpoint.md)). Both use point-in-time recovery.
- **Agent:**
  - the AgentCore runtime (`PYTHON_3_12`, entry point `["opentelemetry-instrument", "main.py"]` per ADR 0002), with its role scoped to the list in the [#13 spec](13-conversation-steps.md);
  - AgentCore Memory ([memory spec](memory.md));
  - the Guardrail ([#12](12-guardrail.md));
  - the standards Knowledge Base on S3 Vectors with its ingestion custom resource ([#17](17-standards-grounding.md)).
- **API:**
  - the REST API with chat (streaming), `GET /me`, review and analytics routes ([#25](25-chat-endpoint.md), [#11](11-identity.md), [#27](27-review-api.md), [#29](29-analytics-api.md));
  - the stream sync Lambda ([#28](28-athena-sync.md));
  - the inactivity sweep and its schedule ([#25](25-chat-endpoint.md)).
- **Lambdas:** every function gets its own role with only the permissions its spec lists. TypeScript functions run on Node.js 24, and Python functions on Python 3.12.
- **Log groups:** every log group, including the AgentCore runtime's, is created in the stack with an explicit retention value and KMS encryption. Read access is limited to a named operator role.

### The deploy script

One command, run from the infra package. In order, it:
1. **Checks the account.** The target account must equal the expected account passed in.
2. **Checks prerequisites:**
   - Bedrock model access for the configured models, failing with a message naming any missing model;
   - CloudWatch Transaction Search. If it is off, the script adds the Logs resource policy and turns it on, then waits for `ACTIVE` (ADR 0002 measured 64 seconds).
3. **Builds the agent zip** with ARM64 Linux wheels (ADR 0002) and uploads it under a new key.
4. **Deploys** the artifacts stack, then the application stack, passing the code key, stack name and `disposable` flag.
5. **Uploads data:** the producer table, peer catalog and seeded records ([#7](07-synthetic-data.md), [#37](37-seeded-records.md)).
6. **Builds and publishes the web app** to the stack's bucket and invalidates CloudFront.
7. **Runs a smoke check** of the API health and the Knowledge Base, and prints the outputs.

It is safe to re-run. It writes a deployment log and prints the total elapsed time, which #40 uses.

### Outputs

Web URL, API URL, runtime ARN, memory ID, Knowledge Base ID, Guardrail ID and version, the table names, bucket names and Athena workgroup.

### CI

- Continuous integration keeps running checks on every PR. It adds the template tests below and `cdk synth` for the full stack.
- Automatic deployment stays limited to publishing the web app (the existing OIDC role).
- Full-stack deploys run the script by hand.

## Testing Decisions

Template tests, using `aws-cdk-lib/assertions` on the synthesized stack:
- every bucket, table and log group is KMS-encrypted;
- every log group has a retention value set;
- no resource has a hard-coded physical name;
- the runtime role's actions equal the [#13 spec](13-conversation-steps.md) list exactly;
- with `disposable=true`, nothing is retained;
- with `disposable=false`, the stateful resources are retained;
- two stacks synthesized with different names share no resource names.

Script checks, run once in the sandbox: a re-run with no changes succeeds, and a missing model access fails with the named message.

## Out of Scope

- Production controls: Okta, WAF, Organizations (documented in the handoff, not built)
- Multi-region deploys

## Further Notes

### Not decided (do not build or assume)

- Retention period for each log group. It is a required deploy-time configuration value with no default, so every deployer chooses it explicitly.
- Whether message content may appear in AgentCore logs at all (ADR 0002). Turning content capture off is a configuration value. ADR 0002 found the Strands tracer still logs content when the documented setting is off, so whoever turns it off must verify the result the same way the spike did.
- The sign-in stand-in ([#11](11-identity.md)), which the stack will host once decided
