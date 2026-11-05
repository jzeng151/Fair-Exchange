"""Producer records: a producer's own certification scope, Premium projects and safe survey context (issue #14).

Read from the producer data files the generator writes (fx_data.generator, issue #7) and built into
records when loaded, so the tool can filter by producer ID in memory (#14 spec).

Survey answers are reduced to per-question summaries, from the #14 spec's ALLOWLIST of farming, water and
practice questions. Every other question (harassment, borrowing, medical access, child schooling,
committees, ...) is never read: the generator does not even copy it. A summary is only given when at least
MIN_RESPONSES distinct survey responses answered, so no single response can be picked out, and a
multiple-choice answer is only named when at least MIN_RESPONSES responses chose it. (Not "households":
about half of the sample's survey rows are not household surveys.) Each fact's period comes from the
responses behind that fact.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from fx_data.tables import GENERATED_DIR, read_table

MIN_RESPONSES = 5

SOURCE_SURVEY = "FTUSA survey responses"

# Answers that are not an answer. Left out of every summary.
NON_ANSWERS = {"", "refused", "don't know", "don’t know", "i don't know", "none of the above applies"}

# The #14 spec's allowlist (default deny). It excludes land-conversion columns (compliance-sensitive) and
# household drinking-water details, and says certification status is never read (checking status is out
# of scope, #21). Adding a column needs a spec change.
# Yes/No practice questions -> how to say "Yes" in a sentence.
YES_NO_FIELDS = {
    "has_hired_labor_code": "hire workers",
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
    "water_access_sources_name": "Water sources",
    "adaption_strategies_name": "How fishers have adapted",
    "future_concerns_name": "Main concern for the future of fishing",
}
# Numbers -> how to describe the median. The sample records a missing number as 0, so 0 is left out.
NUMBER_FIELDS = {
    "farm_area_ha_nbr": "Median farm area, in hectares",
    "yield_produced_per_hectare_nbr": "Median yield produced per hectare (in the unit the survey recorded)",
}
# Multiple-choice questions allowed through (by question label).
MULTI_FIELDS = {
    "harvest_change_reason_core": "Reasons given for the change in harvest",
    "income_sources_ms_core": "Other income sources",
    "ft_benefits_ms_core": "Benefits of Fair Trade named",
}

# Single-choice columns copied into the survey table, besides the response year.
ALLOWED_FIELDS = set(YES_NO_FIELDS) | set(CHOICE_FIELDS) | set(NUMBER_FIELDS)


def _answer(value) -> str | None:
    value = str(value if value is not None else "").strip()
    return None if value.lower() in NON_ANSWERS else value


def _years(years: list) -> str:
    years = sorted({str(y) for y in years if y})
    return years[0] if len(years) == 1 else f"{years[0]}-{years[-1]}" if years else "date unknown"


def _fact(column: str, text: str, years: list, n: int) -> dict:
    """`years` are those of the responses behind this fact; `n` is how many distinct responses."""
    return {"column": column, "text": text, "source": SOURCE_SURVEY, "period": _years(years), "responses": n}


def _survey_facts(responses: list[dict]) -> list[dict]:
    """`responses`: rows of the survey table, one per survey response (allowlisted columns, the response
    year, and one list of choices per multiple-choice question)."""
    facts = []
    for field, phrase in YES_NO_FIELDS.items():
        answered = [(r, a) for r in responses if (a := _answer(r.get(field)))]
        if len(answered) >= MIN_RESPONSES:
            yes = sum(a.lower() == "yes" for _, a in answered) / len(answered)
            facts.append(_fact(field, f"{yes:.0%} of {len(answered)} survey responses say they {phrase}.",
                               [r["response_year"] for r, _ in answered], len(answered)))
    for field, question in CHOICE_FIELDS.items():
        answered = [(r, a) for r in responses if (a := _answer(r.get(field)))]
        if len(answered) >= MIN_RESPONSES:
            top = Counter(a for _, a in answered).most_common(3)
            shares = "; ".join(f"{a} ({n / len(answered):.0%})" for a, n in top)
            facts.append(_fact(field, f"{question}, {len(answered)} survey responses: {shares}.",
                               [r["response_year"] for r, _ in answered], len(answered)))
    for field, question in NUMBER_FIELDS.items():
        answered = [(r, r[field]) for r in responses if r.get(field)]
        if len(answered) >= MIN_RESPONSES:
            value = median(v for _, v in answered)
            facts.append(_fact(field, f"{question}, {len(answered)} survey responses: {value:,.1f}.",
                               [r["response_year"] for r, _ in answered], len(answered)))
    for field, question in MULTI_FIELDS.items():
        picked = {}  # survey response ID -> (row, its real answers); "Other" and non-answers left out
        for r in responses:
            choices = {c.strip() for c in r.get(field) or [] if _answer(c) and c.strip().lower() != "other"}
            if choices:
                picked[r["survey_response_id"]] = (r, choices)
        if len(picked) >= MIN_RESPONSES:  # distinct responses, not selections
            by_choice = Counter(c for _, choices in picked.values() for c in choices)
            # Name an answer only if at least MIN_RESPONSES distinct responses chose it.
            top = [(c, n) for c, n in sorted(by_choice.items(), key=lambda kv: (-kv[1], kv[0]))
                   if n >= MIN_RESPONSES][:3]
            named = "; ".join(f"{c} ({n} responses)" for c, n in top) or \
                f"no single answer was given by {MIN_RESPONSES} or more"
            facts.append(_fact(field, f"{question}, {len(picked)} survey responses: {named}.",
                               [r["response_year"] for r, _ in picked.values()], len(picked)))
    return facts


def build_records(root: Path = GENERATED_DIR) -> dict:
    """Each producer's record from the generated tables."""
    projects: dict[str, list[dict]] = defaultdict(list)
    for p in read_table("premium_projects", root):
        projects[p["producer_id"]].append(p)
    surveys: dict[str, list[dict]] = defaultdict(list)
    for r in read_table("survey_responses", root):
        surveys[r["producer_id"]].append(r)
    scopes = {c["producer_id"]: c["certification_scope"] for c in read_table("certifications", root)}
    records = {}
    for producer in read_table("producers", root):
        pid = producer["producer_id"]
        rows = surveys.get(pid, [])
        facts = _survey_facts(rows)
        if facts:
            note = None
        elif rows:
            note = f"Fewer than {MIN_RESPONSES} survey responses answered each question, so nothing is summarized."
        else:
            note = "No survey responses on record for this producer."
        records[pid] = {
            "certification_scope": scopes.get(pid),
            "premium_projects": sorted(projects.get(pid, []), key=lambda p: (p["start_year"] or 0, p["project_id"])),
            "survey": {"responses": len(rows), "facts": facts, "note": note},
        }
    return records


class ProducerRecords:
    def __init__(self, records: dict):
        self._records = records

    @classmethod
    def load(cls, root: Path = GENERATED_DIR) -> "ProducerRecords":
        return cls(build_records(root))

    def get(self, producer_id: str) -> dict | None:
        return self._records.get(producer_id)

    def items(self, producer_id: str) -> list[dict]:
        """This producer's record as data-tool items (#17 contract): certification scope, own Premium
        projects, then survey summaries. An empty list when there is no record."""
        record = self.get(producer_id)
        if record is None:
            return []
        scope = record["certification_scope"]
        items = [_item(f"Your certification record [{producer_id}]",
                       f"Certification scope: {scope}." if scope else "No certification scope on record.",
                       None, {"certification_scope": scope})]
        for p in record["premium_projects"]:
            year = p["start_year"]
            items.append(_item(f"Your Premium project: {p['title']} [{p['project_id']}]",
                               f"Your Premium project \"{p['title']}\"" + (f", started {year}" if year else "")
                               + f": {p['description']}", str(year) if year else None,
                               {"category": p["category"], "sub_category": p["sub_category"], "year": year,
                                "amount": p["amount"], "description": p["description"]}))
        for f in record["survey"]["facts"]:
            # A summary across responses (#14 spec), so the ID names the producer's summary of one column,
            # never one survey response.
            ref = "SV-" + hashlib.sha1(f"{producer_id}|{f['column']}".encode()).hexdigest()[:6].upper()
            items.append(_item(f"Your {f['period']} survey: {f['column']} [{ref}]", f["text"], f["period"],
                               {"column": f["column"], "responses": f["responses"]}))
        return items


def _item(source: str, text: str, period: str | None, data: dict) -> dict:
    return {"source": source, "kind": "producer_record", "text": text, "period": period, "strength": "exact",
            "data": data}
