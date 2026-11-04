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

Amazon Bedrock AgentCore Evaluations runs the scripted scenarios and the labeled set against a disposable copy of the stack (decided 2026-11-04).
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

- **Stack.** The eval deploys a disposable stack (`FairExchangeEval`, `disposable=true`, [#5](05-cdk-stack.md)), runs, writes the report, and tears the stack down.
- **Runner.** The bedrock-agentcore SDK's on-demand evaluation dataset runner. Its agent invoker sends each scenario's turns to the agent runtime as [#13](13-conversation-steps.md) `start`, `message` and `action` requests. The conversation ID is the runtime session ID.
- **Runtime access.** The eval runner's role may invoke the eval stack's runtime. This adds a third allowed caller to the [#25](25-chat-endpoint.md) rule, for eval stacks only.
- **Dataset:**
  - the scenarios S1 to S7 ([#35](35-scenarios-and-labels.md));
  - the 30 labeled accounts, each run as a short conversation: the account as the intake message, then confirm and `internal` consent;
  - the adversarial scope set ([#34](34-negative-scope-tests.md)).
  - Reference inputs are the human reference tags and each scenario's expected outcomes.

### Evaluators

| Evaluator | Type | Level | What it scores |
|---|---|---|---|
| `tag_overlap` | Code-based (Lambda) | Session | Jaccard of the record's agent `tags` against the reference tags. |
| `citation_validity` | Code-based (Lambda) | Session | Fraction of the record's claims whose source ID is in the decision log's tool references, whose clause exists and was retrieved, and whose section matches the source kind (rules from [#17](17-standards-grounding.md)). |
| `answer_completeness` | Code-based (Lambda) | Session | 1 if the answer had at least one insight and one peer example (`evidence: full`), else 0. Scenarios expected to be limited, like S3, are reported separately. |
| `directive_language` | Code-based (Lambda) | Session | 1 if no claim contains a directive phrase from the shared list ([#17](17-standards-grounding.md)), else 0. |
| `enablement_tone` | Custom model-graded (LLM as judge) | Trace (the answer turn) | 1 to 5 against a written rubric: informs, doesn't instruct, hands the decision back, plain language. |
| `scope_leak` | Code-based (Lambda) | Session | For the adversarial set: 0 if no claim, tool reference or record field holds the other producer's data, else 1. |

- **Data source.** Code-based evaluators read the conversation's saved record from the eval stack's records table by session ID, rather than relying on message content in traces. That keeps them working if content capture is turned off ([#5](05-cdk-stack.md)).
- **Limits.** Each Lambda evaluator runs with a 60-second timeout and read-only access to the eval stack's records table.

### Distinctness and the report

- **Distinctness.** After the run, the runner script takes each contrast pair (S1 and S7, plus the pairs listed in the scenario file) and computes the Jaccard of their cited source IDs. A pair is distinct when it is 0.5 or lower.
- **Report.** One JSON and Markdown report per run, stored in the eval package's results folder and committed for runs used in the demo. It holds:
  - mean tag overlap, with the human-human agreement next to it;
  - citation validity;
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
| Scope leaks | 0 | Vision document |
| Distinct contrast pairs | All | Vision document |
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

## Out of Scope

- Online (sampled, continuous) evaluation of live traffic
- FTUSA's existing benchmark corpus (the vision document accepts a small workshop-made set)

## Further Notes

### Decisions made while writing this spec

- Evaluators read the saved record by session ID rather than trace content.
- A contrast pair counts as distinct at a cited-source Jaccard of 0.5 or lower.
- The tone target is 4 or higher on a 1 to 5 rubric.
