# eval/

Measures FEX against the Vision doc's success metrics.

| Metric | Target | Issue |
|---|---|---|
| Challenge-tag agreement with human labels | ≥ 80% | #36 |
| Claims with a citation and standard clause | 100% | #36 |
| Cross-producer data returned | 0 | #34 |
| Distinct answers for different producer profiles | yes | #36 |
| Enablement tone (no directive phrases; shared list in `agent/src/fex/tone.py`) | yes | #36 |
| AI usage per conversation (tokens, small vs. large model) | tracked | — |

- `scenarios/`: scripted demo scenarios (3+, at least one in Spanish), issue #35. See [`scenarios/README.md`](scenarios/README.md)
- `labeled/challenge-tags.jsonl`: fifteen producer statements (JSON lines) with two labelers' independent tags and a settled `reference`, issue #35; the reference inputs for tag-accuracy scoring (#36)
- `tests/`: pytest harness; can also feed AgentCore Evaluations
  - `test_negative_scope.py` (#34): every data tool in `ALL_TOOLS`, called as every sample producer, with another producer's identity and location slipped into the input. Checks the result is unchanged, holds no account id, and belongs to the session producer. A new tool fails until it gets a scope check in `TOOL_CHECKS`. Run with `cd agent && uv run pytest ../eval/tests`.
- `tests/test_standards_kb_smoke.py`: seam 3 smoke test for the standards Knowledge Base (#17); runs only when `FEX_STANDARDS_KB_ID` is set, as `infra/deploy.sh` does
- `src/fx_evals/`: the eval harness ([spec 36](../docs/specs/36-eval-harness.md)). It runs the dataset (S1 to S7, the contrast runs, the 15 labeled accounts and, once it exists, the #34 adversarial set) through the agent, then scores each conversation from its saved record and eval evidence:
  - `runner.py`: the scenario runner (#35), shared by the offline run, the seam 1 test and the AgentCore Evaluations agent invoker
  - `evaluators.py`: `tag_overlap` (labeled accounts), `citation_validity`, `claim_support` and `enablement_tone` (judge model), `answer_completeness`, `directive_language`, `scope_leak` (#34's exact-ID check and private markers)
  - `distinctness.py`: #7's contrast pairs; the reviewer marks each pair in `contrast_marks.json` (`{"run_id": ..., "marks": {"C1": "tailored"}}`), and only marks for the reported run count
  - `judge.py`: Amazon Nova Pro through Bedrock Converse. Its scores count toward targets only after `judge_calibration.json` records an agreement at or above its threshold (spec 36)
  - Run it offline: `cd agent && PYTHONPATH=../eval/src uv run python -m fx_evals.offline --demo-models` (no AWS; tag and PII outcomes are informational), or `--judge bedrock` without `--demo-models` for the real models and judge. Reports go to `eval/results/`, with the run's sessions in `<run>.sessions.json`; after marking the contrast pairs for that run, `--rescore eval/results/<run>.sessions.json` scores it again so the marks count. Whether sample-derived text may appear in a committed report waits on FTUSA (spec 34) and is not decided, so don't commit reports from real-model runs yet.
