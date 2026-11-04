"""Producer records: a producer's own profile, Premium projects and safe survey context (issue #14).

    PYTHONPATH=src uv run python -m fx_data.records   # offline: writes producer_records.json

Survey answers are reduced to shares of survey responses, from an ALLOWLIST of farming, water and
practice questions. Every other question (harassment, borrowing, medical access, child schooling,
committees, income, ...) is never read into the output. A share is only reported when at least
MIN_RESPONSES distinct survey responses answered, so no single response can be picked out. (Not
"households": about half of the sample's survey rows are not household surveys.) Each fact's period
comes from the responses behind that fact.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from fx_data.peers import (ACCOUNTS_CSV, LINKED_DIR, PROJECTS_CSV, _PLACEHOLDER, build_profiles,
                           build_status_index, resolve_status, tag_for, unique_project_ref)

HERE = Path(__file__).parent
RECORDS_PATH = HERE / "producer_records.json"
SINGLE_CSV = LINKED_DIR / "Survey Response Questions Single Choice.csv"
MULTI_CSV = LINKED_DIR / "Survey Response Questions Multiple Choice.csv"
HEADER_CSV = LINKED_DIR / "Survey Response Header.csv"  # dates for the multiple-choice answers

MIN_RESPONSES = 5

SOURCE_ACCOUNT = "FTUSA producer account (sample data)"
SOURCE_PROJECT = "FTUSA Premium project (sample data, own record)"
SOURCE_SURVEY = "FTUSA survey responses (sample data)"

# Answers that are not an answer. Left out of every share.
NON_ANSWERS = {"", "refused", "don't know", "don’t know", "i don't know", "none of the above applies"}

# The #14 spec's allowlist excludes land-conversion columns (compliance-sensitive) and household
# drinking-water details, and says certification status is never read (checking status is out of
# scope, #21). Only certification scope is kept. Adding a column needs a spec change.
# Yes/No practice questions -> how to say "Yes" in a sentence.
YES_NO_FIELDS = {
    "has_soil_conservation_practices_code": "use soil conservation practices",
    "has_water_conservation_practices_code": "use water conservation practices",
    "has_water_contamination_prevention_practices_code": "take steps to prevent water contamination",
    "has_forest_protection_practices_code": "use forest protection practices",
    "has_received_fertilizer_training_code": "have received fertilizer training",
    "has_noticed_fishing_changes_code": "have noticed changes in fishing",
}
# Questions with named answers -> a short description of the question.
CHOICE_FIELDS = {
    "harvest_changed_code": "How the harvest has changed",
    "has_integrated_pest_management_practices_name": "Pest management practice used",
    "adaption_strategies_name": "How fishers have adapted",
    "future_concerns_name": "Main concern for the future of fishing",
}
# Multiple-choice questions allowed through (by question label).
MULTI_FIELDS = {"harvest_change_reason_core": "Reasons given for the change in harvest"}

ALLOWED_FIELDS = set(YES_NO_FIELDS) | set(CHOICE_FIELDS)


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _answer(value: str | None) -> str | None:
    value = (value or "").strip()
    return None if value.lower() in NON_ANSWERS else value


def _years(dates: list[str]) -> str:
    years = sorted({d[:4] for d in dates if d})
    return years[0] if len(years) == 1 else f"{years[0]}-{years[-1]}" if years else "date unknown"


def _fact(text: str, dates: list[str], n: int) -> dict:
    """`dates` are those of the responses behind this fact; `n` is how many distinct responses."""
    return {"text": text, "source": SOURCE_SURVEY, "period": _years(dates), "responses": n,
            "strength": "exact"}


def _survey_facts(rows: list[dict], reasons: list[dict]) -> list[dict]:
    """`rows`: one dict per survey response. `reasons`: one dict per selected reason
    ({"response": id, "choice": text, "date": text}); a response can select several."""
    facts = []
    for field, phrase in YES_NO_FIELDS.items():
        answered = [(r, a) for r in rows if (a := _answer(r[field]))]
        if len(answered) >= MIN_RESPONSES:
            yes = sum(a.lower() == "yes" for _, a in answered) / len(answered)
            facts.append(_fact(f"{yes:.0%} of {len(answered)} survey responses say they {phrase}.",
                               [r["response_date"] for r, _ in answered], len(answered)))
    for field, question in CHOICE_FIELDS.items():
        answered = [(r, a) for r in rows if (a := _answer(r[field]))]
        if len(answered) >= MIN_RESPONSES:
            top = Counter(a for _, a in answered).most_common(3)
            shares = "; ".join(f"{a} ({n / len(answered):.0%})" for a, n in top)
            facts.append(_fact(f"{question}, {len(answered)} survey responses: {shares}.",
                               [r["response_date"] for r, _ in answered], len(answered)))
    for label, question in MULTI_FIELDS.items():
        picked = [x for x in reasons if (a := _answer(x["choice"])) and a.lower() != "other"]
        responses = {x["response"] for x in picked}  # distinct responses, not selections
        if len(responses) >= MIN_RESPONSES:
            by_choice: dict[str, set[str]] = defaultdict(set)
            for x in picked:
                by_choice[x["choice"].strip()].add(x["response"])
            # Name a reason only if at least MIN_RESPONSES distinct responses gave it.
            top = [(c, len(s)) for c, s in sorted(by_choice.items(), key=lambda kv: (-len(kv[1]), kv[0]))
                   if len(s) >= MIN_RESPONSES][:3]
            if top:
                shares = "; ".join(f"{c} ({n} responses)" for c, n in top)
                facts.append(_fact(f"{question}, {len(responses)} survey responses: {shares}.",
                                   [x["date"] for x in picked], len(responses)))
    return facts


def build_records() -> dict:
    accounts = {r["account_sk"]: r for r in _read(ACCOUNTS_CSV)}
    profiles = build_profiles()["profiles"]
    status_index = build_status_index()
    seen_refs: Counter = Counter()
    projects: dict[str, list[dict]] = defaultdict(list)
    for row in _read(PROJECTS_CSV):
        texts = [row[f] for f in ("translated_project_name", "translated_project_description_txt",
                                  "translated_project_reason_txt", "translated_primary_goal_txt")]
        if any(_PLACEHOLDER.search(x or "") for x in texts):
            continue  # lorem-ipsum test rows are not evidence (same rule as the peer table)
        status = resolve_status(status_index, row)
        ref = unique_project_ref(seen_refs, row["account_sk"], row["translated_project_name"],
                                 row["translated_project_description_txt"])
        projects[row["account_sk"]].append({
            "project_ref": ref, "source": f"{SOURCE_PROJECT} {ref}",
            "challenge_tag": tag_for(row["subcategory"], *texts), "subcategory": row["subcategory"] or None,
            "name": texts[0], "action": texts[1], "challenge": texts[2], "intended_outcome": texts[3],
            "status": status.get("project_status_name") or None,
            "start_date": status.get("project_start_date") or None,
            "end_date": status.get("project_end_date") or None,
        })

    survey_rows: dict[str, list[dict]] = defaultdict(list)
    for row in _read(SINGLE_CSV):
        if row["account_sk"] in accounts:
            survey_rows[row["account_sk"]].append(
                {k: row[k] for k in ALLOWED_FIELDS | {"response_date"}} | {"response": row["survey_response_sk"]})
    response_dates = {r["survey_response_sk"]: r["recorded_date"] or r["end_date"] or r["start_date"]
                      for r in _read(HEADER_CSV)}
    reasons: dict[str, list[dict]] = defaultdict(list)
    for row in _read(MULTI_CSV):
        if row["account_sk"] in accounts and row["question_label_txt"] in MULTI_FIELDS:
            reasons[row["account_sk"]].append({"response": row["survey_response_sk"],
                                               "choice": row["question_choice_txt"],
                                               "date": response_dates.get(row["survey_response_sk"], "")})

    records = {}
    for pid, account in accounts.items():
        rows = survey_rows.get(pid, [])
        facts = _survey_facts(rows, reasons.get(pid, []))
        if facts:
            note = None
        elif rows:
            note = f"Fewer than {MIN_RESPONSES} survey responses answered each question, so nothing is summarized."
        else:
            note = "No survey responses on record for this producer."
        records[pid] = {
            "profile": {
                **profiles[pid],
                "certification_scope": account["certification_scope_name"] or None,
                "supply_chain_role": account["raw_supply_chain_role_txt"] or None,
                "source": SOURCE_ACCOUNT,
            },
            "premium_projects": sorted(projects.get(pid, []), key=lambda p: p["start_date"] or ""),
            "survey": {"responses": len(rows), "facts": facts, "note": note},
        }
    return {"description": "Each sample producer's own record: profile, Premium projects and survey summary "
                           f"(allowlisted fields only, at least {MIN_RESPONSES} distinct survey responses per share).",
            "records": records}


class ProducerRecords:
    def __init__(self, table: dict):
        self._records = table["records"]

    @classmethod
    def load(cls, path: Path = RECORDS_PATH) -> "ProducerRecords":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def get(self, producer_id: str) -> dict | None:
        return self._records.get(producer_id)


def main() -> None:
    table = build_records()
    RECORDS_PATH.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    recs = table["records"].values()
    print(f"wrote {RECORDS_PATH}: {len(table['records'])} producers, "
          f"{sum(bool(r['premium_projects']) for r in recs)} with projects, "
          f"{sum(bool(r['survey']['facts']) for r in recs)} with survey facts, "
          f"{sum(r['survey']['responses'] > 0 for r in recs)} with any survey responses", file=sys.stderr)


if __name__ == "__main__":
    main()
