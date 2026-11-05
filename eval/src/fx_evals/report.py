"""Scores every session and builds the one report (spec 36): JSON plus Markdown."""
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from fex.models import DeclinedRecord
from fx_data.standards import Standards

from fx_evals import evaluators as ev
from fx_evals.distinctness import pair_rows
from fx_evals.judge import Judge
from fx_evals.runs import EVAL
from fx_evals.session import Session

CALIBRATION = EVAL / "judge_calibration.json"  # written by the calibration step; absent = not calibrated
JUDGE_EVALUATORS = {"claim_support", "enablement_tone"}


def judge_calibrated(judge: Judge | None, path: Path = CALIBRATION) -> bool:
    """True once the calibration recorded for this judge model met its threshold (spec 36)."""
    if judge is None or not path.exists():
        return False
    cal = json.loads(path.read_text(encoding="utf-8"))
    return cal.get("model_id") == judge.model_id and all(
        cal.get(k) is not None and cal[k] >= cal["threshold"] for k in ("tone_agreement", "support_agreement"))


def outcome_checks(s: Session, real_services: bool = True) -> list[dict]:
    """A scenario or contrast run's expected outcome against what happened. With the demo model, tags need
    the real model and the PII fields need the real scanner, so those checks are informational there.
    Out-of-scope handling waits on #21 and isn't checked."""
    exp, record = s.run.expected, s.record
    actual = {
        "record_status": record.status if record else None,
        "consent_scope": record.consent.scope if record else None,
        "evidence": s.answer_evidence,
        "pii_flag": getattr(record, "pii_flag", False) if record else None,
        "pii_entity_types": list(getattr(record, "pii_entity_types", [])) if record else None,
        "tags": sorted(getattr(record, "tags", [])) if record else None,
    }
    needs = {"tags": "the real model", "pii_flag": "the real PII scanner", "pii_entity_types": "the real PII scanner"}
    return [{"run_id": s.run.run_id, "field": f, "expected": sorted(exp[f]) if f == "tags" else exp[f],
             "actual": actual[f], "pass": actual[f] == (sorted(exp[f]) if f == "tags" else exp[f]),
             "informational": None if real_services else needs.get(f)} for f in actual if f in exp]


def score(sessions: list[Session], judge: Judge | None, run_id: str, marks: dict | None = None,
          real_services: bool = True) -> dict[str, Any]:
    standards, ownership = Standards.load(), ev.Ownership()
    results, failures, outcomes = [], [], []
    for s in sessions:
        if s.run.kind in ("scenario", "contrast"):
            outcomes += outcome_checks(s, real_services)
        if s.record is not None or s.evidence is not None:
            results.append(ev.scope_leak(s, ownership))  # whatever the producer saw, however the run ended
        if s.problems or s.record is None:
            failures.append({"run_id": s.run.run_id, "problems": s.problems or ["no saved record"]})
            continue
        if isinstance(s.record, DeclinedRecord):
            if s.run.kind in ("labeled", "scope"):  # only scenarios expect a decline (spec 36)
                failures.append({"run_id": s.run.run_id, "problems": ["the conversation was declined, so no "
                                                                      "completed record to score"]})
            continue  # a declined scenario is scored only on its expected outcome
        if s.run.kind == "labeled":
            results.append(ev.tag_overlap(s))
        results += [ev.citation_validity(s, standards), ev.claim_support(s, judge), ev.answer_completeness(s),
                    ev.directive_language(s), ev.enablement_tone(s, judge)]
    pairs = pair_rows({s.run.run_id: s for s in sessions}, run_id, marks)
    calibrated = judge_calibrated(judge)
    return {
        "run_id": run_id, "generated_at": datetime.now(UTC).isoformat(),
        "judge": {"model_id": judge.model_id if judge else None, "calibrated": calibrated},
        "summary": summarize(results, sessions, pairs, calibrated),
        "real_services": real_services,
        "failures": failures, "outcomes": outcomes, "pairs": pairs, "results": results,
    }


def _values(results: list[dict], name: str, keep=lambda r: True) -> list[float]:
    return [r["value"] for r in results if r["evaluator"] == name and r["value"] is not None and keep(r)]


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def summarize(results: list[dict], sessions: list[Session], pairs: list[dict], calibrated: bool) -> dict:
    labeled = [s.run for s in sessions if s.run.kind == "labeled" and s.run.labeler_tags]
    expected_limited = lambda r: r["breakdown"].get("expected") == "limited"  # noqa: E731
    marked = [p for p in pairs if p["passes"] is not None]
    directive = [r for r in results if r["evaluator"] == "directive_language"]
    metrics = {
        "mean_tag_overlap": _mean(_values(results, "tag_overlap")),
        "human_tag_agreement": _mean([ev.jaccard(*r.labeler_tags) for r in labeled]),
        "citation_validity": _mean(_values(results, "citation_validity")),
        "claim_support": _mean(_values(results, "claim_support")),
        "answer_completeness": _mean(_values(results, "answer_completeness", lambda r: not expected_limited(r))),
        "answer_completeness_expected_limited": _mean(_values(results, "answer_completeness", expected_limited)),
        "directive_language_claims": sum(len(r["breakdown"]["matches"]) for r in directive),
        "directive_language_rate": _mean([r["value"] for r in directive]),
        "mean_tone_score": _mean(_values(results, "enablement_tone")),
        "distinct_pairs_tailored": sum(p["passes"] for p in marked),
        "distinct_pairs_marked": len(marked),
        "distinct_pairs_total": len(pairs),
        "pairs_awaiting_marks": [p["pair"] for p in pairs if p["mark_status"] != "marked"],
        "scope_leak_count": sum(1 for r in results if r["evaluator"] == "scope_leak" and r["value"] == 1.0),
        "unscored": {name: sum(1 for r in results if r["evaluator"] == name and r["value"] is None)
                     for name in sorted({r["evaluator"] for r in results})},
    }
    m = metrics
    targets = [
        ("Mean tag overlap", "0.80 or higher", m["mean_tag_overlap"], lambda v: v >= 0.80, True),
        ("Citation validity", "1.0", m["citation_validity"], lambda v: v == 1.0, True),
        ("Scope leaks", "0", m["scope_leak_count"], lambda v: v == 0, True),
        ("Distinct contrast pairs (marked tailored)", "All",
         m["distinct_pairs_tailored"] if not m["pairs_awaiting_marks"] else None,
         lambda v: v == m["distinct_pairs_total"], True),
        ("Directive language", "0 claims", m["directive_language_claims"], lambda v: v == 0, True),
        ("Mean tone score", "4 or higher", m["mean_tone_score"], lambda v: v >= 4, calibrated),
        ("Claim support", "no target yet", m["claim_support"], lambda v: None, calibrated),
    ]
    metrics["targets"] = [{"metric": name, "target": goal, "value": value, "counted": counted,
                           "met": None if value is None or not counted else check(value)}
                          for name, goal, value, check, counted in targets]
    return metrics


def _fmt(v: Any) -> str:
    return "n/a" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v)


def markdown(report: dict) -> str:
    s = report["summary"]
    lines = [f"# Eval run {report['run_id']}", "",
             f"Judge: {report['judge']['model_id'] or 'none'} "
             f"({'calibrated' if report['judge']['calibrated'] else 'not calibrated: its scores are reported, not counted'})",
             "", "| Metric | Target | Value | Met |", "|---|---|---|---|"]
    for t in s["targets"]:
        met = "not counted" if not t["counted"] else {True: "yes", False: "no", None: "n/a"}[t["met"]]
        lines.append(f"| {t['metric']} | {t['target']} | {_fmt(t['value'])} | {met} |")
    lines += ["", f"- Human-human tag agreement: {_fmt(s['human_tag_agreement'])} (next to the mean tag overlap)",
              f"- Answer completeness: {_fmt(s['answer_completeness'])}; runs expected to be limited: "
              f"{_fmt(s['answer_completeness_expected_limited'])}",
              f"- Directive-language rate (sessions with none): {_fmt(s['directive_language_rate'])}",
              f"- Pairs awaiting a current mark: {', '.join(s['pairs_awaiting_marks']) or 'none'}",
              f"- Unscored sessions per evaluator: {s['unscored']}"]
    if report["failures"]:
        lines += ["", "## Run failures", ""] + [f"- {f['run_id']}: {'; '.join(f['problems'])}" for f in report["failures"]]
    checked = [o for o in report["outcomes"] if not o["informational"]]
    misses = [o for o in report["outcomes"] if not o["pass"]]
    lines += ["", "## Outcome checks", "", f"{sum(o['pass'] for o in checked)} of {len(checked)} checked outcomes pass."]
    lines += [f"- {o['run_id']} {o['field']}: expected {o['expected']}, got {o['actual']}"
              + (f" (informational: needs {o['informational']})" if o["informational"] else "") for o in misses]
    lines += ["", "## Contrast pairs", ""]
    for p in report["pairs"]:
        lines.append(f"### {p['pair']}: {' vs '.join(p['runs'])} ({p['tag']}; differ in {', '.join(p['differ_in'])})")
        lines.append(f"Jaccard {_fmt(p['jaccard'])}" + (" (diagnostic only: shared region and crop)" if p["mark_only"] else "")
                     + f"; mark: {p['mark'] or p['mark_status']}")
        for run, ans in p["answers"].items():
            if ans.get("missing"):
                lines.append(f"- {run}: no completed record")
            else:
                lines.append(f"- {run}: " + " | ".join(ans["insights"] + ans["peer_examples"]))
        lines.append("")
    return "\n".join(lines) + "\n"


def write(report: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / f"{report['run_id']}.json", out_dir / f"{report['run_id']}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    return json_path, md_path
