"""Run the eval in this process (#36): every run drives the agent entrypoint, records go to a temporary
folder and eval evidence to memory, then everything is scored into one report.

    cd agent && PYTHONPATH=../eval/src uv run python -m fx_evals.offline --demo-models    # no AWS at all
    cd agent && PYTHONPATH=../eval/src uv run python -m fx_evals.offline --judge bedrock  # real models, Nova Pro

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
from fex.eval_evidence import InMemoryEvidenceStore
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo-models", action="store_true", help="the deterministic demo model; no AWS")
    ap.add_argument("--judge", choices=["none", "bedrock"], default="none",
                    help="none leaves tone and claim support unscored")
    ap.add_argument("--runs", help="comma-separated run IDs (default: every run)")
    ap.add_argument("--out", default=str(EVAL / "results"))
    args = ap.parse_args(argv)
    runs = all_runs()
    if args.runs:
        wanted = set(args.runs.split(","))
        runs = [r for r in runs if r.run_id in wanted]
    judge: Judge | None = BedrockJudge() if args.judge == "bedrock" else None
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory() as tmp:
        report = score(run_all(runs, Path(tmp), args.demo_models), judge, run_id,
                       real_services=not args.demo_models)
    json_path, md_path = write(report, Path(args.out))
    print(f"eval report: {json_path} and {md_path}")
    failed_outcomes = [o for o in report["outcomes"] if not o["pass"] and not o["informational"]]
    return 1 if report["failures"] or failed_outcomes else 0


if __name__ == "__main__":
    sys.exit(main())
