"""The distinctness check (spec 36): #7's contrast pairs, each producer with its own run.

The number is a diagnostic: the Jaccard of the two answers' cited peer, regional and clause IDs, own-record
sources left out. The target is the reviewer mark. A team member reads each pair side by side and marks it
"tailored" or "generic" in eval/contrast_marks.json for a given run; a mark from another run is stale and
counts as pending. A high number never overrides a "tailored" mark.
"""
import json
import re
from pathlib import Path

from fx_evals.evaluators import jaccard
from fx_evals.runs import EVAL, MARK_ONLY_PAIRS, PAIR_RUNS, contrast_pairs
from fx_evals.session import Session

MARKS = EVAL / "contrast_marks.json"
DISTINCT_AT_MOST = 0.5
CATALOG_ID = re.compile(r"\[(CAT-[^\]]+)\]")


def cited_ids(session: Session) -> set[str] | None:
    """The final answer's cited peer, regional and clause IDs, classified by the tool result's kind.
    None when the evidence is missing, since sources can't be classified without it."""
    record = session.completed
    if record is None or session.evidence is None:
        return None
    ids = set()
    for claim in list(record.insights) + list(record.peer_examples):
        ids.add(f"clause:{claim.citation.standard_clause}")
        item = session.evidence.item_for(claim.citation.source)
        kind = item["kind"] if item else None
        if kind == "peer":
            match = CATALOG_ID.search(claim.citation.source)
            ids.add(f"peer:{match.group(1) if match else claim.citation.source}")
        elif kind == "regional":
            ids.add(f"regional:{claim.citation.source}")
    return ids


def load_marks(path: Path = MARKS) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"run_id": None, "marks": {}}


def pair_rows(sessions: dict[str, Session], run_id: str, marks: dict | None = None) -> list[dict]:
    marks = marks if marks is not None else load_marks()
    current = marks.get("marks", {}) if marks.get("run_id") == run_id else {}
    rows = []
    for pair in contrast_pairs():
        a, b = PAIR_RUNS[pair["pair_id"]]
        left, right = sessions.get(a), sessions.get(b)
        ids = [cited_ids(s) if s else None for s in (left, right)]
        number = jaccard(*ids) if None not in ids else None
        mark = current.get(pair["pair_id"])
        stale = pair["pair_id"] in marks.get("marks", {}) and not mark
        rows.append({
            "pair": pair["pair_id"], "runs": [a, b], "tag": pair["tag"], "differ_in": pair["differ_in"],
            "jaccard": number, "diagnostic_distinct": None if number is None else number <= DISTINCT_AT_MOST,
            "mark_only": pair["pair_id"] in MARK_ONLY_PAIRS,
            "mark": mark, "mark_status": "stale" if stale else ("pending" if mark is None else "marked"),
            "passes": None if mark is None else mark == "tailored",
            "answers": {run: _answer(sessions.get(run)) for run in (a, b)},
        })
    return rows


def _answer(session: Session | None) -> dict:
    record = session.completed if session else None
    if record is None:
        return {"missing": True}
    return {"producer_id": record.producer_id, "insights": [c.text for c in record.insights],
            "peer_examples": [c.text for c in record.peer_examples]}
