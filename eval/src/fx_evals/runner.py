"""The on-demand eval run (spec [36](https://github.com/jzeng151/Fair-Exchange/issues/36)).

Wires the AgentCore Evaluations runner (verified SDK surface in `agent/.venv`):
`OnDemandEvaluationDatasetRunner(region="us-west-2").run(config=EvaluationRunConfig(...),
dataset=Dataset(scenarios=[Scenario(...)]), agent_invoker=<scenario invoker>,
span_collector=<CloudWatchAgentSpanCollector>)`, then evaluates the conversations the invoker
drove (records table [#26](https://github.com/jzeng151/Fair-Exchange/issues/26) + evidence
bucket [#34](https://github.com/jzeng151/Fair-Exchange/issues/34)) and writes the report.

The live CLI is `uv run python -m fx_evals.runner --api-base <deployed chat API>`; the offline
deterministic path lives in `eval/tests/test_eval_harness.py` (stub transports, no AWS).
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from fex.models import CompletedRecord, DeclinedRecord
from fx_evals.evaluators import jaccard
from fx_evals.sessions import ReferenceData, Session

RESULTS_DIR = Path(__file__).resolve().parents[3] / "eval" / "results"


def repo_root() -> Path:
    """The fair-exchange mono-repo root (`eval/src/fx_evals/runner.py` -> root)."""
    return Path(__file__).resolve().parents[3]


def load_scenarios(scenarios_dir: Path) -> list[dict[str, Any]]:
    """The scenario fixtures: one JSON object per file ([#35](https://github.com/jzeng151/Fair-Exchange/issues/35))."""
    scenarios: list[dict[str, Any]] = []
    for path in sorted(scenarios_dir.glob("*.json")):
        scenario = json.loads(path.read_text())
        if not scenario.get("id") or not scenario.get("producer_id"):
            raise AssertionError(f"scenario fixture missing id/producer_id: {path.name}")
        scenarios.append(scenario)
    if not scenarios:
        raise AssertionError(f"no scenario files in {scenarios_dir}")
    return scenarios


def load_reference(scenarios: list[dict[str, Any]]) -> dict[str, ReferenceData]:
    """Per-scenario reference: `expect.tags` + needles from the OTHER producers' profiles.

    The reference tags are what the confirmed playback should get ([#35], `expect.tags`).
    The scope-leak evaluator needs strings that must never appear in this conversation:
    every other sample producer's id plus the region/organization fragments of their notes.
    """
    references: dict[str, ReferenceData] = {}
    for scenario in scenarios:
        scenario_id = str(scenario["id"])
        expect = scenario.get("expect") or {}
        references[scenario_id] = ReferenceData(
            scenario_id=scenario_id,
            reference_tags=[str(tag) for tag in expect.get("tags") or ()],
            forbidden=_forbidden_needles(scenario, scenarios),
        )
    return references


def _forbidden_needles(
    scenario: dict[str, Any],
    scenarios: list[dict[str, Any]],
) -> list[str]:
    own_note = str(scenario.get("profile_note") or "").lower()
    needles: list[str] = []
    for other in scenarios:
        if str(other.get("id")) == str(scenario.get("id")):
            continue
        needles.append(str(other.get("producer_id")))
        for fragment in str(other.get("profile_note") or "").split(","):
            head = fragment.split(".")[0].strip()
            if len(head) >= 4 and head.lower() not in own_note:
                # Attributes the current producer's own profile shares (e.g. a school
                # name) are not leaks of the other producers' data (#36).
                needles.append(head)
    return needles


def distinctness_violation(
    session_a: Session,
    session_b: Session,
    *,
    max_jaccard: float = 0.5,
) -> bool:
    """The distinctness check (spec): Jaccard on cited peer/regional/clause IDs > max fails.

    A declared contrast pair (two producers sharing a challenge, #35 S1/S7 rule) must
    differ: no verbatim repeats of the cited peer, regional and clause data.
    """
    def _cited(session: Session) -> set[str]:
        record = session.record
        if getattr(record, "insights", None) is None:
            return set()
        # source label -> tool-item kind from captured evidence (#36: classify by the
        # data tools' source contract rather than the synthetic test prefixes alone)
        kinds: dict[str, str] = {}
        if session.evidence is not None:
            for item in session.evidence.tool_items:
                item_source = str(item.get("source") or "")
                if item_source:
                    kinds[item_source] = str(item.get("kind") or "")
        labels: set[str] = set()
        for claim in list(record.insights) + list(record.peer_examples):
            citation = claim.citation
            labels.add(f"clause:{citation.standard_clause}")
            source = citation.source
            kind = kinds.get(source, "")
            if kind == "peer" or source.startswith("peer-project:"):
                # Real peer labels: `Premium project, <organization> [<catalog_id>]` —
                # the bracketed id is the stable identifier; synthetic test labels
                # (`peer-project:P-…`) keep the full source string.
                match = re.search(r"\[([^]]+)\]\s*$", source)
                labels.add(f"peer:{match.group(1) if match else source}")
            elif kind == "regional" or source.startswith("regional:"):
                labels.add(f"regional:{source}")
            # every other kind (producer record / standards) is producer-specific or
            # shared by design — it cannot signal copied answers.
        return labels

    left, right = _cited(session_a), _cited(session_b)
    union = left | right
    if not union:
        return False
    return jaccard(left, right) > max_jaccard


def build_dataset(
    scenarios: list[dict[str, Any]],
    references: dict[str, ReferenceData],
) -> list[dict[str, Any]]:
    """One AgentCore Scenario per fixture: assertions + reference inputs ride in metadata."""
    entries: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_id = str(scenario["id"])
        reference = references[scenario_id]
        entries.append({
            "scenario_id": scenario_id,
            "assertions": sorted(reference.reference_tags),
            "metadata": {
                "scenario_id": scenario_id,
                "producer_id": str(scenario["producer_id"]),
                "reference_tags": reference.reference_tags,
                "forbidden": list(reference.forbidden),
            },
        })
    return entries


def human_tag_agreement(
    sessions_by_scenario: dict[str, Session],
    references: dict[str, ReferenceData],
) -> float | None:
    """Human-human tag agreement (spec 36 report bullet: shown next to mean tag
    overlap): the mean Jaccard between the human reference labels and each
    reviewer's corrected tags, over the sessions a reviewer has marked.

    A session whose record carries no reviewer tags is excluded, not a 0 —
    with no marked sessions at all the agreement is None."""
    values = []
    for scenario_id, session in sorted(sessions_by_scenario.items()):
        reviewer_tags = getattr(session.record, "reviewer_tags", None) or []
        if not reviewer_tags:
            continue
        values.append(jaccard(reviewer_tags, references[scenario_id].reference_tags))
    return sum(values) / len(values) if values else None


def summarize(results: list[dict[str, Any]], distinctness: dict[str, Any],
              human_tag_agreement: float | None = None) -> dict[str, Any]:
    """Report summary (#36 spec: the one-report means and rates; the human-human
    agreement rides next to mean_tag_overlap per the spec's report bullets)."""
    def mean(evaluator_id: str) -> float | None:
        # None (unscored — e.g. no evidence capture) is excluded, not a 0 (#36).
        values = [r["value"] for r in results
                  if r["evaluator_id"] == evaluator_id and r["value"] is not None]
        return sum(values) / len(values) if values else None

    pairs_checked = distinctness.get("pairs_checked", 0)
    violations = distinctness.get("violations", [])
    return {
        "mean_tag_overlap": mean("tag_overlap"),
        "human_tag_agreement": human_tag_agreement,
        "citation_validity": mean("citation_validity"),
        "answer_completeness": mean("answer_completeness"),
        "directive_language_violations": sum(
            1 for r in results
            if r["evaluator_id"] == "directive_language" and r["value"] == 0.0),
        "mean_tone_score": mean("enablement_tone"),
        "distinctness_pass_rate": (
            (pairs_checked - len(violations)) / pairs_checked) if pairs_checked else None,
        "scope_leak_count": sum(
            1 for r in results if r["evaluator_id"] == "scope_leak" and r["value"] != 0.0),
        "pairs_awaiting_reviewer_marks": len(distinctness.get("marks_pending", [])),
    }


def outcome_checks(
    scenario: dict[str, Any],
    record: CompletedRecord | DeclinedRecord | None,
) -> list[dict[str, Any]]:
    """Compare the saved record against the scenario's expected outcome block."""
    expected = scenario.get("expect", {}).get("record")
    if not expected or record is None:
        return []
    checks = []
    field_map = {
        "status": record.status,
        "consent_scope": record.consent.scope,
        # feedback/pii_flag sit on CompletedRecord itself; DeclinedRecord has neither
        "feedback": getattr(record, "feedback", None),
        "pii_flag": getattr(record, "pii_flag", False),
    }
    for field, actual in field_map.items():
        if field in expected:
            checks.append({
                "scenario_id": scenario["id"], "field": field,
                "expected": expected[field], "actual": actual,
                "pass": actual == expected[field],
            })
    return checks


def run_offline(
    *,
    scenarios: list[dict[str, Any]],
    references: dict[str, ReferenceData],
    transport_factory: Any,
    stores: Any,
    evaluator_registry: Any,
    judge: Any,
    contrast_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drive every scenario, evaluate the saved sessions and return the report dict."""
    from fx_evals.evaluators import run_evaluators
    from fx_evals.scenario_runner import drive

    driven: list[tuple[dict[str, Any], str]] = []
    for scenario in scenarios:
        driven.append((scenario, drive(scenario, transport_factory())))
    sessions: list[tuple[dict[str, Any], Session]] = []
    failures: list[dict[str, str]] = []
    for scenario, session_id in driven:
        try:
            record = stores.get_record(session_id)
            evidence = stores.get_evidence(session_id)
        except LookupError:
            # Spec #36: a labeled account with no completed record is a run
            # failure: reported and excluded from the tag mean, never scored 0.
            failures.append({"session_id": session_id, "error": "no saved record"})
            continue
        sessions.append((scenario, Session(session_id=session_id, record=record,
                                           evidence=evidence)))
    runner_fn = evaluator_registry or run_evaluators
    results: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for scenario, session in sessions:
        reference = references[str(scenario["id"])]
        if isinstance(session.record, DeclinedRecord):
            # The declined path has no shown answer: feeding it to the evaluators
            # distorts every mean with a degenerate row, so it gets outcome checks
            # only (#36).
            outcomes.extend(outcome_checks(scenario, session.record))
            continue
        results.extend(runner_fn(session, reference, judge))
        outcomes.extend(outcome_checks(scenario, session.record))
    sessions_by_scenario = {str(scenario["id"]): session
                            for scenario, session in sessions}
    distinctness = build_distinctness(
        sessions_by_scenario,
        contrast_config if contrast_config is not None else load_contrast_config())
    return {
        "results": results,
        "failures": failures,
        "summary": summarize(
            results, distinctness,
            human_tag_agreement=human_tag_agreement(sessions_by_scenario, references)),
        "outcomes": outcomes,
        "distinctness": distinctness,
    }


CONTRAST_PAIRS_PATH = repo_root() / "eval" / "contrast_pairs.json"


def load_contrast_config(path: Path | None = None) -> dict[str, Any]:
    """The declared contrast pairs + reviewer marks (`eval/contrast_pairs.json`).

    The authoritative pair list lands with the #7 generator's producer definitions
    file; until then the declared pairs live in the config file, not the code.
    """
    resolved = path or CONTRAST_PAIRS_PATH
    if not resolved.exists():
        return {"pairs": [], "reviewer_marks": {}}
    data = json.loads(resolved.read_text())
    return {"pairs": list(data.get("pairs") or []),
            "reviewer_marks": dict(data.get("reviewer_marks") or {})}


def distinctness_pairs(
    sessions_by_scenario: dict[str, Session],
    *,
    pairs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The declared cross-producer contrast pairs (#7/#36): Jaccard > 0.5 fails.

    Pairs come from the contrast config, never from within-producer grouping: the
    spec's contrast partners (S1/S7 style) are different producers who share a
    challenge tag — a generic agent would answer both identically.
    """
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        left, right = str(pair.get("a") or ""), str(pair.get("b") or "")
        missing = [s for s in (left, right) if s and s not in sessions_by_scenario]
        rows.append({
            "a": left, "b": right, "basis": pair.get("basis"),
            "missing": missing,
            "violation": None if missing else distinctness_violation(
                sessions_by_scenario[left], sessions_by_scenario[right]),
        })
    return rows


def pair_answers(
    sessions_by_scenario: dict[str, Session],
    rows: list[dict[str, Any]],
    reviewer_marks: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Side-by-side answers per checked pair (a reviewer marks each tailored/generic)."""
    marks = reviewer_marks or {}

    def side(scenario_id: str) -> dict[str, Any]:
        record = sessions_by_scenario[scenario_id].record
        return {
            "scenario_id": scenario_id,
            "producer_id": str(record.producer_id),
            "insights": [claim.text for claim in (record.insights or [])],
            "peer_examples": [claim.text for claim in (record.peer_examples or [])],
        }

    blocks: list[dict[str, Any]] = []
    for row in rows:
        key = f"{row['a']}|{row['b']}"
        blocks.append({
            "pair": f"{row['a']} vs {row['b']}", "basis": row["basis"],
            "sides": [side(s) for s in (row["a"], row["b"])
                      if s in sessions_by_scenario],
            "reviewer_mark": marks.get(key),
        })
    return blocks


def build_distinctness(
    sessions_by_scenario: dict[str, Session],
    contrast_config: dict[str, Any],
) -> dict[str, Any]:
    """The distinctness block: checked rows, violations, side-by-side answers,
    and the reviewer marks wiring (spec 36: a human marks each pair 'tailored'
    or 'generic'; a generic mark is itself a violation, and pairs still awaiting
    a mark are listed in marks_pending rather than counted as violations)."""
    rows = distinctness_pairs(
        sessions_by_scenario, pairs=list(contrast_config.get("pairs") or []))
    marks = dict(contrast_config.get("reviewer_marks") or {})
    violations: list[str] = []
    for row in rows:
        key = f"{row['a']} vs {row['b']}"
        if marks.get(f"{row['a']}|{row['b']}") == "generic":
            violations.append(f"{key} (reviewer marked generic)")
        elif row["missing"]:
            violations.append(
                f"{key} (unchecked: missing {', '.join(row['missing'])})")
        elif row["violation"]:
            violations.append(key)
    return {
        "pairs_checked": len(rows),
        "violations": violations,
        "marks_pending": [f"{row['a']} vs {row['b']}" for row in rows
                          if marks.get(f"{row['a']}|{row['b']}") not
                          in ("tailored", "generic")],
        "pair_answers": pair_answers(sessions_by_scenario, rows, marks),
    }


def write_report(report: dict[str, Any], results_dir: Path = RESULTS_DIR) -> list[Path]:
    """Write the JSON + Markdown report pair; returns the paths."""
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "last-eval-run.json"
    md_path = results_dir / "last-eval-run.md"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    lines = ["# Eval run", ""]
    summary = report.get("summary", {})
    for key, value in summary.items():
        lines.append(f"- {key}: "
                     + (f"{value:.3f}" if isinstance(value, float) else str(value)))
    for failure in report.get("failures", []):
        lines.append(f"- RUN FAILURE: {failure['session_id']}: {failure['error']}")
    for check in report.get("outcomes", []):
        mark = "ok" if check["pass"] else "MISMATCH"
        lines.append(f"- outcome {check['scenario_id']} {check['field']}: "
                     f"expected {check['expected']}, got {check['actual']} [{mark}]")
    for result in report["results"]:
        value = result["value"]
        shown = "n/a" if value is None else f"{value:.2f}"
        lines.append(f"- {result['evaluator_id']} {result['session_id']}: {shown}")
    distinct = report["distinctness"]
    lines.append(f"- distinctness: {distinct['pairs_checked']} checked, "
                 f"{len(distinct['violations'])} violations")
    for block in distinct.get("pair_answers", []):
        mark = block.get("reviewer_mark") or "(pending reviewer mark)"
        lines.append(f"- pair {block['pair']} [{mark}]")
        for side in block["sides"]:
            claims = side["insights"] + side["peer_examples"]
            text = " | ".join(claims) if claims else "(no claims)"
            lines.append(f"  - {side['scenario_id']}: {text}")
    md_path.write_text("\n".join(lines) + "\n")
    return [json_path, md_path]


def main() -> None:
    """The live CLI: drives the deployed chat API, then evaluates from the record table."""
    parser = argparse.ArgumentParser(description="Run the FEX evaluation suite (#36)")
    parser.add_argument("--scenarios", default="eval/scenarios",
                        help="scenario fixtures dir (repo-relative or absolute)")
    parser.add_argument("--api-base", default=os.environ.get("EVAL_API_BASE", ""),
                        help="the deployed chat API (env EVAL_API_BASE)")
    parser.add_argument("--out", default=str(RESULTS_DIR))
    args = parser.parse_args()
    from fx_evals.evaluators import run_evaluators
    from fx_evals.judge import BedrockToneJudge
    from fx_evals.scenario_runner import HttpChatTransport, drive
    from fx_evals.sessions import (
        evidence_bucket_from_env,
        records_table_from_env,
    )

    if not args.api_base:
        raise SystemExit("--api-base or EVAL_API_BASE must name the deployed chat API")
    scenarios_path = Path(args.scenarios)
    if not scenarios_path.is_absolute():
        scenarios_path = repo_root() / scenarios_path
    scenarios = load_scenarios(scenarios_path)
    references = load_reference(scenarios)

    records = records_table_from_env()
    evidence = evidence_bucket_from_env()
    judge = BedrockToneJudge.from_env()
    transport = HttpChatTransport(args.api_base)

    driven: list[tuple[dict[str, Any], str]] = []
    for scenario in scenarios:
        driven.append((scenario, drive(scenario, transport)))
    sessions: list[tuple[dict[str, Any], Session]] = []
    failures: list[dict[str, str]] = []
    for scenario, session_id in driven:
        try:
            record = records.get(session_id)
            evidence_obj = evidence.get(session_id)
        except LookupError:
            failures.append({"session_id": session_id, "error": "no saved record"})
            continue
        sessions.append((scenario, Session(session_id=session_id, record=record,
                                           evidence=evidence_obj)))
    results: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for scenario, session in sessions:
        results.extend(run_evaluators(session, references[str(scenario["id"])], judge))
        outcomes.extend(outcome_checks(scenario, session.record))
    sessions_by_scenario = {str(scenario["id"]): session
                            for scenario, session in sessions}
    distinctness = build_distinctness(sessions_by_scenario, load_contrast_config())
    report = {
        "results": results,
        "failures": failures,
        "summary": summarize(results, distinctness,
                             human_tag_agreement(sessions_by_scenario, references)),
        "outcomes": outcomes,
        "distinctness": distinctness,
    }
    json_path, md_path = write_report(report, Path(args.out))
    print(f"eval report: {json_path} + {md_path}")


if __name__ == "__main__":
    main()