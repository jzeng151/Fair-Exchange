# Spec: Scripted scenarios and labeled set (#35)

Status: approved for build, 2026-11-04. Revised 2026-11-05: synthetic scenario producers and contrast runs.

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
  - `turns`: an ordered list of `{message: text}` or `{action: {name, args}}` entries, using the [#13](13-conversation-steps.md) actions. Each turn names the step it expects (`expect_step`), and the last turn is always `end`;
  - `intake_replies`: scripted answers the runner sends, in order, when FEX asks more intake questions than the turns cover. When they run out, it sends "That's all I can add."
  - `expected`: record status, consent scope, evidence (`full` or `limited`), PII flag and entity types, tags, and whether out-of-scope handling occurs.
- **Required scenarios:**

| ID | Producer | Language | Path |
|---|---|---|---|
| S1 | `SYN-001`: Colombian coffee smallholder, Cauca | en | Drought; correction in playback; consent `internal`; feedback |
| S2 | `SYN-002`: Mexican coffee cooperative | es | Price drop; consent `internal_and_outward` |
| S3 | `SYN-003`: Vietnamese coffee processor | en | Labor shortage; the regional tool returns nothing, so the answer has no regional insight |
| S4 | `SYN-004`: Honduran coffee cooperative | es | Starts describing a challenge, then declines at consent |
| S5 | `SYN-005`: Côte d'Ivoire cocoa cooperative | en | Names a person and gives a phone number; PII flag |
| S6 | `SYN-006`: Côte d'Ivoire cocoa smallholder | en | Asks for certification status (out of scope), then describes a labor challenge. The out-of-scope expectation is checked only once the #21 detection function is decided; until then S6 checks the in-scope part only. |
| S7 | `SYN-005`: Côte d'Ivoire cocoa cooperative | en | Contrast partner of S1: same tag (climate and weather), different crop and region; used for distinctness (#7 pair C1) |

- **Producers (decided 2026-11-05).** The scenario producers are #7's synthetic producers, listed once in `scenario_producers` in #7's producer definitions. S5 and S7 share a producer. Each has a full synthetic record, projects and surveys.
- **Contrast runs.** Each producer in #7's `contrast_pairs` needs a scenario run for the distinctness check ([#36](36-eval-harness.md)). S1 to S7 cover `SYN-001`, `SYN-002`, `SYN-003`, `SYN-005` and `SYN-006` (S6 is C3's run for `SYN-006`). `SYN-007` and `SYN-008` get their own files in `eval/scenarios/contrast/`. Only S1 to S7 sit at the top of `eval/scenarios/`: the web picker and the demo sign-in allow-list read that folder.
- **Demo set.** S1 to S5 make up the minimum demo run-through (README), with S6 added once its detection is decided. S2 and S4 cover Spanish.
- **Runner behavior.** The scenario runner reads each turn's response stream to the end, through the `done` event, and checks the expected `step` and `actions` before sending the next turn. `step` and `actions` arrive before the turn finishes saving, and the turn lock rejects an early next request with 409 ([#25](25-chat-endpoint.md)). It answers extra intake questions from `intake_replies`. It fails a scenario if an expected step doesn't arrive within 60 seconds. The same runner is used by #34, #36 and #40.

### Labeled set

- **Contents (decided 2026-11-04 as part of the minimum set).** 15 short scripted producer accounts of a challenge, the text a producer would type in intake. They are spread across the 11 tags, in English and Spanish, and written by the team from the scenario producers and the sample's project reasons.
- **Running them.** Each account has a `producer_id` from the producer table and runs as a scenario: the account as the intake message, `intake_replies`, `confirm_playback`, `set_consent` `internal`, then `end`.
- **Producers for live runs.** Not decided (do not build or assume). Live eval runs capture tool results in eval evidence, which needs the FTUSA confirmation in [#34](34-negative-scope-tests.md).
- **Labeling.**
  - Two team members tag each account independently with any number of the 11 tags, without seeing FEX's output.
  - Their agreement (mean Jaccard, same as the eval metric) is reported.
  - Disagreements are settled by discussion into one reference label set per account.
- **Storage.** One JSON lines file with the account text, `producer_id`, language, both labelers' tags and the reference tags. These become the reference inputs for AgentCore Evaluations ([#36](36-eval-harness.md)).
- **Labelers** must not tune prompts against the labeled set before the first eval run is recorded.

## Testing Decisions

- **File checks (eval package):**
  - every scenario file validates against its schema, and every scenario ends with `end`;
  - every `producer_id` exists in the producer table;
  - each scenario's producer matches #7's `scenario_producers`, and every producer in #7's `contrast_pairs` has a scenario run;
  - every action is a valid [#13](13-conversation-steps.md) action;
  - the required scenarios S1 to S7 exist, and no other JSON file sits at the top of `eval/scenarios/`;
  - every label uses only the 11 tags.
- **Seam 1:** S1 to S7 run against the agent entrypoint with a scripted fake model and a fake PII scanner. Their expected outcomes are checked, except tags, which need the real model.
- **Deployed smoke test:** against the deployed API, consecutive turns wait for `done` and the end of the response stream before the next request, without receiving a turn-lock 409.

## Out of Scope

- Running and scoring the evals ([#36](36-eval-harness.md))
- The redeploy timing ([#40](40-timed-redeploy.md))
