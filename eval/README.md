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
