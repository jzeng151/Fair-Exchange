# Spec: Evaluation with AgentCore Evaluations (#36)

Status: approved for build, 2026-11-04. Should-have. Revised 2026-11-05: claim-support evaluator, judge model, contrast pairs from #7, how the runner reaches the agent.

## Problem Statement

FTUSA already measures its AI with a five-metric harness, and the MVP should be measurable the same way. The vision document's targets are:
- at least 80% tag agreement with human labels;
- every claim cited;
- different answers for producers with different profiles;
- an enablement tone.

Without a repeatable eval, these are claims made in a demo, not measurements.

## Solution

Amazon Bedrock AgentCore Evaluations (decided 2026-11-04) runs the scripted scenarios and the labeled set against a dedicated eval copy of the stack.
- **Scoring.** Code-based evaluators (Lambda functions) score each conversation's saved record against the reference labels. Model-graded evaluators score tone and whether each claim's cited source supports its wording.
- **Comparison.** A small runner script compares scenario pairs for distinctness.
- **Output.** One report.

## User Stories

1. As an FTUSA reviewer, I want tag accuracy measured against human labels with a clear definition, so that the 80% target means something.
2. As an FTUSA reviewer, I want every claim checked for a valid citation, so that grounding is measured.
3. As an FTUSA reviewer, I want producers who share a challenge but differ in profile shown to get different answers, so that answers aren't generic.
4. As an FTUSA reviewer, I want tone scored for directive language, so that FEX informs rather than instructs.
5. As an FTUSA engineer, I want the results in AgentCore Evaluations and in one report file, so that we can rerun and compare them with our existing harness.
6. As an FTUSA engineer, I want the eval to run on a disposable stack, so that eval records never mix with demo or reviewer data.
7. As an FTUSA reviewer, I want each claim checked against the fact it cites, so that a correct citation attached to wrong wording is caught.

## Implementation Decisions

### Running it

- **Stack.** One eval stack, `FairExchangeEval`, deployed with `disposable=true` and `evalAccess=true` ([#5](05-cdk-stack.md)). It is deployed once when eval work starts, reused for every run so prompt changes can be tested quickly, and destroyed at the end of the event. Agent changes reach it through a normal redeploy.
- **Runner.** The bedrock-agentcore SDK's on-demand evaluation dataset runner. Its agent invoker is the scenario runner from [#35](35-scenarios-and-labels.md): it waits for each expected step, answers extra intake questions, and ends every conversation with `end`. The conversation ID is the runtime session ID.
- **Runtime access.** The `evalAccess` eval runner role ([#5](05-cdk-stack.md), [#25](25-chat-endpoint.md)). The invoker calls the agent runtime directly, not the chat API, so eval producers never need to be on the demo sign-in allow-list. The chat API's own turn handling is covered by the deployed smoke test in [#35](35-scenarios-and-labels.md).
- **Dataset:**
  - the scenarios S1 to S7 ([#35](35-scenarios-and-labels.md));
  - the contrast runs for #7's producer pairs that S1 to S7 don't cover (`eval/scenarios/contrast/`, [#35](35-scenarios-and-labels.md));
  - the 15 labeled accounts, each run as defined in [#35](35-scenarios-and-labels.md), with its own `producer_id` and a complete action sequence ending in `end`;
  - the adversarial scope set ([#34](34-negative-scope-tests.md)).
  - Reference inputs are the human reference tags and each scenario's expected outcomes.

### Evaluators

| Evaluator | Type | Level | What it scores |
|---|---|---|---|
| `tag_overlap` | Code-based (Lambda) | Session | Jaccard of the record's agent `tags` against the reference tags. Labeled accounts only. |
| `citation_validity` | Code-based (Lambda) | Session | Fraction of shown claims whose source was among the tool results in the eval evidence, whose clause exists and was retrieved, and whose section matches the source kind (rules from [#17](17-standards-grounding.md)). |
| `claim_support` | Code-based (Lambda) calling a judge model | Session | Fraction of shown claims whose cited tool result, taken from the eval evidence, supports the claim's wording. The Lambda sends each claim with the text of the tool result it cites to the judge model. A claim whose source isn't in the eval evidence is left to `citation_validity` and not judged. |
| `answer_completeness` | Code-based (Lambda) | Session | 1 if the answer had at least one insight and one peer example (`evidence: full`), else 0. Scenarios whose expected evidence is `limited` are reported separately. |
| `directive_language` | Code-based (Lambda) | Session | 1 if no claim contains a directive phrase from the shared list ([#17](17-standards-grounding.md)), else 0. |
| `enablement_tone` | Code-based (Lambda) calling a judge model | Session | 1 to 5 against a written rubric (informs, doesn't instruct, hands the decision back, plain language). The Lambda sends the shown claims from the eval evidence to a Bedrock judge model. |
| `scope_leak` | Code-based (Lambda) | Session | 0 if no leak appears in the eval evidence or record, else 1. For the adversarial set: none of the other producer's private markers. For every other session: the exact-ID check. Both rules are in [#34](34-negative-scope-tests.md). Answers the producer saw before a reopen or retry are scanned too. |

- **Data source.** Evaluators read the conversation's record and its eval evidence object ([#34](34-negative-scope-tests.md)) by session ID, never message content in traces. That keeps them working if content capture is turned off ([#5](05-cdk-stack.md)).
- **Missing or declined records.** A labeled account with no completed record is a run failure: it is reported and excluded from the tag mean, never scored as zero overlap. A declined scenario is scored only on its expected outcome.
- **Limits.** Each Lambda evaluator runs with a 60-second timeout and read-only access to the eval stack's records table and eval evidence bucket. The tone and claim-support evaluators may also invoke the judge model.
- **Judge model.** Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) for both judge evaluators (decided 2026-11-05). It is a different model family from the agent's Claude models, so it doesn't grade its own family's writing, and it needs no Marketplace subscription. Before its scores count toward a target, it is calibrated against hand marks: about 10 answers for tone and about 20 claims for support, supported and unsupported, in English and Spanish. The agreement threshold is written here before calibration runs. Below it, judge scores are reported but don't count toward targets. A malformed or timed-out judge reply leaves that session unscored, never scored as a pass.

### Distinctness and the report

- **Distinctness.** After the run, the runner script takes each contrast pair: #7's pairs C1 to C4 (`contrast_pairs` in #7's producer definitions), each producer with its own scenario run. S1 and S7 are C1's producers, so that pair is counted once. It computes the Jaccard of the pair's cited peer, regional and clause IDs only; each producer's own-record sources are left out, since they always differ. A pair is distinct when that is 0.5 or lower. This number is a diagnostic. The report also shows each pair's answers side by side, and a team member marks each pair "tailored" or "generic". The mark decides the target, and a high number never overrides a "tailored" mark. C4's producers share region and crop, so their regional facts overlap by design; C4 is judged on the mark alone.
- **Report.** One JSON and Markdown report per run, stored in the eval package's results folder and committed for runs used in the demo. It holds:
  - mean tag overlap, with the human-human agreement next to it;
  - citation validity;
  - claim support;
  - answer completeness;
  - directive-language rate;
  - mean tone score;
  - the distinctness pass rate;
  - the scope-leak count;
  - per-scenario outcome checks.

### Targets

| Metric | Target | Source |
|---|---|---|
| Mean tag overlap (Jaccard), decided 2026-11-04 | 0.80 or higher | Vision document |
| Citation validity | 1.0 | Vision document |
| Claim support | Reported only until the judge passes calibration; no target yet | Set here |
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
  - a leak fixture scores 1, and a fixture citing another producer's peer catalog entry (`CAT-`) scores 0;
  - with a stub judge, a claim its cited tool result doesn't support lowers `claim_support`, and a malformed judge reply leaves the session unscored.
- **Runner test,** with the AgentCore client stubbed: a scenario's turns become the right request sequence, and distinctness is computed from fixture records, including a high-overlap pair marked "tailored" passing.
- **Prior art:** the verifier and scope tests.

### Spike check

- The code-based evaluator payload carries the runtime session ID, so evaluators can look up the record and eval evidence.
- **Result (2026-11-05).** A throwaway code-based evaluator ran on a real FEX session (101 spans) and was deleted afterward. The Lambda event has no top-level session ID. The ID is on every span as `attributes["session.id"]`, one value across the session, and in `evaluationReferenceInputs[].context.spanContext.sessionId` when reference inputs are sent. It equals the runtime session ID, which the chat API sets to the conversation ID. Evaluators read the reference-input context first, then the spans' single `session.id`, and fail on zero or several (`fx_evals.session.session_id_from_payload`). This needs the runtime's spans in CloudWatch; they carry `session.id` even with content capture off.

## Out of Scope

- Online (sampled, continuous) evaluation of live traffic
- FTUSA's existing benchmark corpus (the vision document accepts a small workshop-made set)

## Further Notes

### Decisions made while writing this spec

- Evaluators read the saved record and the eval evidence by session ID, never trace content.
- One eval stack is reused across runs rather than deployed per run.
- Distinctness uses cited peer, regional and clause IDs as a diagnostic, plus a side-by-side reviewer judgment for the target.
- The tone target is 4 or higher on a 1 to 5 rubric.

### Decisions made 2026-11-05

- A claim-support evaluator closes the gap left by [#17](17-standards-grounding.md)'s provenance check, which doesn't prove a claim's wording matches its source.
- The judge model is Amazon Nova Pro, calibrated before its scores count.
- Contrast pairs come from #7; the reviewer mark decides each pair, and C4 is judged on the mark alone.
- The invoker calls the agent runtime directly, not the chat API.
- The evaluator Lambdas may read eval evidence ([#34](34-negative-scope-tests.md) matches this).
