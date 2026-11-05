"""Run the eval in this process (#36): every run drives the agent entrypoint, records go to a temporary
folder and eval evidence to memory, then everything is scored into one report.

    cd agent && PYTHONPATH=../eval/src uv run python -m fx_evals.offline --demo-models    # no AWS at all
    cd agent && PYTHONPATH=../eval/src uv run python -m fx_evals.offline --judge bedrock  # real models, Nova Pro
    cd agent && PYTHONPATH=../eval/src uv run python -m fx_evals.offline --rescore ../eval/results/<run>.sessions.json

Each run saves its sessions next to the report. After a reviewer marks the contrast pairs for that run in
eval/contrast_marks.json, --rescore scores the saved sessions again under the same run ID, so the marks
count, without rerunning the conversations.

The deployed path (AgentCore Evaluations on the eval copy of the stack) uses the same runner and
evaluators. Committed reports show answers side by side; whether sample-derived peer text may appear in
a committed report waits on FTUSA (spec 34) and is not decided, so don't commit reports from real-model
runs until it is.
"""
import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fex.conversation import ConversationEngine, InMemoryStateStore
from fex.eval_evidence import EvalEvidence, InMemoryEvidenceStore
from fex.models import parse_record
from fex.records.local import FileRecordStore

from fx_evals.judge import BedrockJudge, Judge
from fx_evals.report import score, write
from fx_evals.runner import InProcessTransport, ScenarioRunner
from fx_evals.runs import EVAL, Run, all_runs
from fx_evals.session import Session


def engine_for(records_dir: Path, evidence: InMemoryEvidenceStore, demo: bool,
               pii_scanner=None) -> ConversationEngine:
    if demo:
        from fex.conversation.demo_model import DemoModel
        from fex.tools.standards import LocalClauseRetriever

        model = DemoModel()
        return ConversationEngine(store=InMemoryStateStore(), small_model=model, large_model=model,
                                  records=FileRecordStore(records_dir), retriever=LocalClauseRetriever(),
                                  pii_scanner=pii_scanner, evidence_store=evidence)
    from fex.conversation.runtime import model_ids
    from fex.guardrail import OutputAssessor, guarded_bedrock_model
    from fex.pii import default_pii_scanner
    from fex.translate import AmazonTranslator

    small, large = model_ids()
    return ConversationEngine(store=InMemoryStateStore(), small_model=guarded_bedrock_model(small),
                              large_model=guarded_bedrock_model(large), records=FileRecordStore(records_dir),
                              pii_scanner=pii_scanner or default_pii_scanner(), output_assessor=OutputAssessor(),
                              translator=AmazonTranslator(), evidence_store=evidence)


def run_all(runs: list[Run], records_dir: Path, demo: bool, pii_scanner=None) -> list[Session]:
    sessions = []
    for run in runs:
        evidence = InMemoryEvidenceStore()
        runner = ScenarioRunner(InProcessTransport(engine_for(records_dir, evidence, demo, pii_scanner)))
        conversation_id = f"eval-{run.run_id}"
        result = runner.run(run, conversation_id)
        path = records_dir / f"{conversation_id}.json"
        record = parse_record(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None
        sessions.append(Session(run=run, conversation_id=conversation_id, record=record,
                                evidence=evidence.get(conversation_id), answer_evidence=result.answer_evidence,
                                problems=result.problems))
    return sessions


def save_sessions(sessions: list[Session], path: Path) -> None:
    path.write_text(json.dumps([{
        "run_id": s.run.run_id, "conversation_id": s.conversation_id,
        "record": s.record.model_dump(mode="json") if s.record is not None else None,
        "evidence": s.evidence.model_dump(mode="json") if s.evidence is not None else None,
        "answer_evidence": s.answer_evidence, "problems": s.problems} for s in sessions], indent=1) + "\n",
        encoding="utf-8")


def load_sessions(path: Path) -> list[Session]:
    runs = {r.run_id: r for r in all_runs()}
    sessions = []
    for item in json.loads(path.read_text(encoding="utf-8")):
        if item["run_id"] not in runs:
            raise SystemExit(f"{path}: run {item['run_id']} is no longer in the dataset")
        sessions.append(Session(
            run=runs[item["run_id"]], conversation_id=item["conversation_id"],
            record=parse_record(item["record"]) if item["record"] is not None else None,
            evidence=EvalEvidence.model_validate(item["evidence"]) if item["evidence"] is not None else None,
            answer_evidence=item["answer_evidence"], problems=item["problems"]))
    return sessions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo-models", action="store_true", help="the deterministic demo model; no AWS")
    ap.add_argument("--judge", choices=["none", "bedrock"], default="none",
                    help="none leaves tone and claim support unscored")
    ap.add_argument("--runs", help="comma-separated run IDs (default: every run)")
    ap.add_argument("--rescore", type=Path, help="a saved <run>.sessions.json to score again, under its run ID")
    ap.add_argument("--out", default=str(EVAL / "results"))
    args = ap.parse_args(argv)
    judge: Judge | None = BedrockJudge() if args.judge == "bedrock" else None
    out = Path(args.out)
    if args.rescore:
        if args.runs:
            ap.error("--runs can't be combined with --rescore")
        run_id = args.rescore.name.removesuffix(".sessions.json")
        old = json.loads((args.rescore.parent / f"{run_id}.json").read_text(encoding="utf-8"))
        sessions, real_services = load_sessions(args.rescore), old["real_services"]
    else:
        runs = all_runs()
        if args.runs:
            wanted = [r.strip() for r in args.runs.split(",") if r.strip()]
            known = {r.run_id for r in runs}
            if unknown := [r for r in wanted if r not in known] or ([] if wanted else ["(none given)"]):
                ap.error(f"unknown run IDs: {', '.join(unknown)}")
            runs = [r for r in runs if r.run_id in wanted]
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        real_services = not args.demo_models
        with tempfile.TemporaryDirectory() as tmp:
            sessions = run_all(runs, Path(tmp), args.demo_models)
        out.mkdir(parents=True, exist_ok=True)
        save_sessions(sessions, out / f"{run_id}.sessions.json")
    report = score(sessions, judge, run_id, real_services=real_services)
    json_path, md_path = write(report, out)
    print(f"eval report: {json_path} and {md_path}")
    failed_outcomes = [o for o in report["outcomes"] if not o["pass"] and not o["informational"]]
    return 1 if report["failures"] or failed_outcomes else 0


if __name__ == "__main__":
    sys.exit(main())
