# Spec: Evaluation with AgentCore Evaluations (#36)

Status: approved for build, 2026-11-04. Should-have.

## Problem Statement

FTUSA already measures its AI with a five-metric harness, and the MVP should be measurable the same way. The vision document's targets are:
- at least 80% tag agreement with human labels;
- every claim cited;
- different answers for producers with different profiles;
- an enablement tone.

Without a repeatable eval, these are claims made in a demo, not measurements.

## Solution

Amazon Bedrock AgentCore Evaluations (decided 2026-11-04) runs the scripted scenarios and the labeled set against a dedicated eval copy of the stack.
- **Scoring.** Code-based evaluators (Lambda functions) score each conversation's saved record against the reference labels. A model-graded evaluator scores tone.
- **Comparison.** A small runner script compares scenario pairs for distinctness.
- **Output.** One report.

## User Stories

1. As an FTUSA reviewer, I want tag accuracy measured against human labels with a clear definition, so that the 80% target means something.
2. As an FTUSA reviewer, I want every claim checked for a valid citation, so that grounding is measured.
3. As an FTUSA reviewer, I want producers who share a challenge but differ in profile shown to get different answers, so that answers aren't generic.
4. As an FTUSA reviewer, I want tone scored for directive language, so that FEX informs rather than instructs.
5. As an FTUSA engineer, I want the results in AgentCore Evaluations and in one report file, so that we can rerun and compare them with our existing harness.
6. As an FTUSA engineer, I want the eval to run on a disposable stack, so that eval records never mix with demo or reviewer data.

## Implementation Decisions

### Running it

- **Stack.** One eval stack, `FairExchangeEval`, deployed with `disposable=true` and `evalAccess=true` ([#5](05-cdk-stack.md)). It is deployed once when eval work starts, reused for every run so prompt changes can be tested quickly, and destroyed at the end of the event. Agent changes reach it through a normal redeploy.
- **Runner.** The bedrock-agentcore SDK's on-demand evaluation dataset runner. Its agent invoker is the scenario runner from [#35](35-scenarios-and-labels.md): it waits for each expected step, answers extra intake questions, and ends every conversation with `end`. The conversation ID is the runtime session ID.
- **Runtime access.** The `evalAccess` eval runner role ([#5](05-cdk-stack.md), [#25](25-chat-endpoint.md)).
- **Dataset:**
  - the scenarios S1 to S7 ([#35](35-scenarios-and-labels.md));
  - the 15 labeled accounts, each run as defined in [#35](35-scenarios-and-labels.md), with its own `producer_id` and a complete action sequence ending in `end`;
  - the adversarial scope set ([#34](34-negative-scope-tests.md)).
  - Reference inputs are the human reference tags and each scenario's expected outcomes.

### Evaluators

| Evaluator | Type | Level | What it scores |
|---|---|---|---|
| `tag_overlap` | Code-based (Lambda) | Session | Jaccard of the record's agent `tags` against the reference tags. Labeled accounts only. |
| `citation_validity` | Code-based (Lambda) | Session | Fraction of shown claims whose source was among the tool results in the eval evidence, whose clause exists and was retrieved, and whose section matches the source kind (rules from [#17](17-standards-grounding.md)). |
| `answer_completeness` | Code-based (Lambda) | Session | 1 if the answer had at least one insight and one peer example (`evidence: full`), else 0. Scenarios expected to be limited, like S3, are reported separately. |
| `directive_language` | Code-based (Lambda) | Session | 1 if no claim contains a directive phrase from the shared list ([#17](17-standards-grounding.md)), else 0. |
| `enablement_tone` | Code-based (Lambda) calling a judge model | Session | 1 to 5 against a written rubric (informs, doesn't instruct, hands the decision back, plain language). The Lambda sends the shown claims from the eval evidence to a Bedrock judge model. |
| `scope_leak` | Code-based (Lambda) | Session | For the adversarial set: 0 if none of the other producer's identifiers appear in the eval evidence or record, else 1 (rules in [#34](34-negative-scope-tests.md)). |

- **Data source.** Evaluators read the conversation's record and its eval evidence object ([#34](34-negative-scope-tests.md)) by session ID, never message content in traces. That keeps them working if content capture is turned off ([#5](05-cdk-stack.md)).
- **Missing or declined records.** A labeled account with no completed record is a run failure: it is reported and excluded from the tag mean, never scored as zero overlap. A declined scenario is scored only on its expected outcome.
- **Limits.** Each Lambda evaluator runs with a 60-second timeout and read-only access to the eval stack's records table and eval evidence bucket. The tone evaluator may also invoke the judge model.

### Distinctness and the report

- **Distinctness.** After the run, the runner script takes each contrast pair (S1 and S7, plus the producer pairs from [#7](07-synthetic-data.md), each with its own scenario run). It computes the Jaccard of the pair's cited peer, regional and clause IDs only; each producer's own-record sources are left out, since they always differ. A pair is distinct when that is 0.5 or lower. This number is a diagnostic. The report also shows each pair's answers side by side, and a team member marks each pair "tailored" or "generic".
- **Report.** One JSON and Markdown report per run, stored in the eval package's results folder and committed for runs used in the demo. It holds:
  - mean tag overlap, with the human-human agreement next to it;
  - citation validity;
  - answer completeness;
  - directive-language rate;
  - mean tone score;
  - the distinctness pass rate;
  - the scope-leak count;
  - per-scenario outcome checks;
  - run failures, so a missing record is visible in the report, not just dropped.

The summary rates are on a 0 to 1 scale: a session's tone is its rubric score divided by 5 (the target of 4 or higher reads as 0.8), the directive-language count is the number of sessions that scored 0 (a directive phrase appeared), and the scope-leak count is the number of sessions that scored 1.0 (a leak scores 1.0, failing the 0 target). Each session's full result block still carries the raw values.

### Targets

| Metric | Target | Source |
|---|---|---|
| Mean tag overlap (Jaccard), decided 2026-11-04 | 0.80 or higher | Vision document |
| Citation validity | 1.0 | Vision document |
| Scope leaks | 0 | Vision document |
| Distinct contrast pairs (reviewer marked "tailored") | All | Vision document |
| Directive language | 0 claims | Vision document (tone) |
| Mean tone score | 4 or higher | Set here; the rubric is reviewed with FTUSA at the closing demo |

## Testing Decisions

- **Evaluator unit tests** (public handler functions, fixture records):
  - Jaccard computed correctly, including empty sets;
  - a claim with a source not in the decision log fails;
  - a peer example citing a regional source fails;
  - a directive phrase in Spanish scores 0;
  - a leak fixture scores 1.
- **Runner test,** with the AgentCore client stubbed: a scenario's turns become the right request sequence, and distinctness is computed from fixture records.
- **Prior art:** the verifier and scope tests.

### Spike check

- The code-based evaluator payload carries the runtime session ID, so evaluators can look up the record and eval evidence.

## Out of Scope

- Online (sampled, continuous) evaluation of live traffic
- FTUSA's existing benchmark corpus (the vision document accepts a small workshop-made set)

## Further Notes

### Decisions made while writing this spec

- Evaluators read the saved record and the eval evidence by session ID, never trace content.
- One eval stack is reused across runs rather than deployed per run.
- Distinctness uses cited peer, regional and clause IDs as a diagnostic, plus a side-by-side reviewer judgment for the target.
- The tone target is 4 or higher on a 1 to 5 rubric.
