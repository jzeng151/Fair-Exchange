# Spec: Scripted scenarios and labeled set (#35)

Status: approved for build, 2026-11-04.

## Problem Statement

The demo needs at least three scripted producer conversations that run end to end, one in Spanish, plus the decline and PII paths. The eval needs a small human-labeled set to measure tag accuracy against. If scripts live in people's heads, demo runs differ and evals can't be repeated.

## Solution

Scenarios are data files. Each file holds the producer, the language, the exact sequence of messages and button actions, and the expected outcomes. The same files drive the demo run-through (#40), the deployed smoke tests and the eval runs ([#36](36-eval-harness.md)). A separate set of about 30 labeled conversations gives the human tag labels.

## User Stories

1. As a tester, I want each demo scenario scripted message by message, so that every run of the demo is the same.
2. As an FTUSA reviewer, I want scenarios covering drought, price drop, labor shortage, Spanish, decline, PII and an out-of-scope request, so that the demo shows every required path.
3. As an FTUSA reviewer, I want each scenario's expected outcome written down, so that a run can be checked as pass or fail.
4. As an evaluator, I want about 30 conversations tagged independently by two people, so that tag accuracy is measured against a trustworthy reference.
5. As an evaluator, I want the agreement between the two human labelers reported, so that we know how hard the tagging task is.

## Implementation Decisions

### Scenario files

- **Format.** One JSON file per scenario in the eval package. Each holds:
  - `scenario_id`, `producer_id` (from the producer table, [#7](07-synthetic-data.md)), `language`;
  - `turns`: an ordered list of `{message: text}` or `{action: {name, args}}` entries, using the [#13](13-conversation-steps.md) actions;
  - `expected`: record status, consent scope, evidence (`full` or `limited`), PII flag and entity types, tags, and whether out-of-scope handling occurs.
- **Required scenarios:**

| ID | Producer | Language | Path |
|---|---|---|---|
| S1 | Colombian coffee smallholder, Cauca | en | Drought; correction in playback; consent `internal`; feedback |
| S2 | Mexican coffee cooperative | es | Price drop; consent `internal_and_outward` |
| S3 | Vietnamese processor | en | Labor shortage; limited evidence (no regional data) |
| S4 | Honduran or Peruvian producer | es | Starts describing a challenge, then declines at consent |
| S5 | Côte d'Ivoire cocoa producer | en | Names a person and gives a phone number; PII flag |
| S6 | Any | en | Asks for certification status (out of scope), then describes a real challenge |
| S7 | Contrast partner of S1 | en | Same tag as S1, different crop or region; used for distinctness |

- **Demo set.** S1 to S6 make up the demo run-through. S2 and S4 cover Spanish.

### Labeled set

- **Contents.** About 30 short scripted producer accounts of a challenge, the text a producer would type in intake. They are spread across the 11 tags, in English and Spanish, and written by the team from the scenario producers and the sample's project reasons.
- **Labeling.**
  - Two team members tag each account independently with any number of the 11 tags, without seeing FEX's output.
  - Their agreement (mean Jaccard, same as the eval metric) is reported.
  - Disagreements are settled by discussion into one reference label set per account.
- **Storage.** One JSON lines file with the account text, language, both labelers' tags and the reference tags. These become the reference inputs for AgentCore Evaluations ([#36](36-eval-harness.md)).
- **Labelers** must not tune prompts against the labeled set before the first eval run is recorded.

## Testing Decisions

- **File checks (eval package):**
  - every scenario file validates against its schema;
  - every `producer_id` exists in the producer table;
  - every action is a valid [#13](13-conversation-steps.md) action;
  - the required scenarios S1 to S7 exist;
  - every label uses only the 11 tags.
- **Seam 1:** S1 to S7 run against the agent entrypoint with a scripted fake model. Their expected outcomes are checked, except tags, which need the real model.

## Out of Scope

- Running and scoring the evals ([#36](36-eval-harness.md))
- The redeploy timing ([#40](40-timed-redeploy.md))
