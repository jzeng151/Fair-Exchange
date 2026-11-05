"""Producer data generator (issue #7, docs/specs/07-synthetic-data.md).

    cd data && uv run --group generator python -m fx_data.generator   # calls Comprehend for new descriptions
    cd data && uv run python -m fx_data.generator --offline           # no AWS; fails if a check is missing

Builds one set of producer data files from FTUSA's sample (docs/olena_data/) and the hand-written inputs
in data/generator_inputs/:
  - producer_definitions.json: the synthetic SYN- producers, their projects, surveys and certification
    scope, and the contrast pairs
  - vocabulary_map.csv: sample crop and structure values -> the #14 vocabulary (unmapped -> "other")
  - subcategory_tags.csv: sample project sub-category -> challenge tags (unmapped -> left out of the catalog)
  - pii_checks.csv: Comprehend PII answers, keyed by the SHA-256 of each catalog description

Writes generated/<table>/<table>.jsonl (fx_data.tables) and generated/report.json. No randomness: names and
IDs come from sorted order and hashes, so the same inputs give byte-identical files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

from fx_data.peers import (_PLACEHOLDER, LINKED_DIR, PROJECTS_CSV, SAMPLE_DIR, _read, _short,
                           build_status_index, fictional_names, fictionalize, resolve_status)
from fx_data.records import ALLOWED_FIELDS, MULTI_FIELDS, NUMBER_FIELDS
from fx_data.regional import COUNTRY_NAMES, country_code
from fx_data.tables import GENERATED_DIR, TABLES, table_path
from fx_data.text import normalize

INPUTS_DIR = Path(__file__).parents[2] / "generator_inputs"
PROJECTS_FILE = PROJECTS_CSV.relative_to(SAMPLE_DIR)
STATUS_FILE = (LINKED_DIR / "Premium Projects Environmental.csv").relative_to(SAMPLE_DIR)
ACCOUNTS_FILE = (LINKED_DIR / "Producer Accounts.csv").relative_to(SAMPLE_DIR)
SINGLE_FILE = (LINKED_DIR / "Survey Response Questions Single Choice.csv").relative_to(SAMPLE_DIR)
MULTI_FILE = (LINKED_DIR / "Survey Response Questions Multiple Choice.csv").relative_to(SAMPLE_DIR)
HEADER_FILE = (LINKED_DIR / "Survey Response Header.csv").relative_to(SAMPLE_DIR)

KEPT_CROPS = {"coffee", "banana", "cocoa"}
OTHER = "other"
SURVEY_COLUMNS = sorted(ALLOWED_FIELDS)

# The #20 rule (#7 spec): these entity types at this score or more are a PII hit. Others, such as DATE_TIME, are not.
PII_TYPES = {"NAME", "PHONE", "EMAIL", "ADDRESS"}
PII_MIN_SCORE = 0.8

# Comprehend answer for one description: [{"Type": "NAME", "Score": 0.99}, ...]
PiiCheck = Callable[[str], list[dict]]


class MissingPiiCheck(RuntimeError):
    """An offline run met a description with no PII check result."""


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------

def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{hashlib.sha1('|'.join(parts).encode()).hexdigest()[:8].upper()}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _blank(value) -> str | None:
    value = (value or "").strip()
    return value or None


def _number(value) -> float | None:
    value = (value or "").strip()
    return float(value) if value else None


def canonical_country(name: str | None) -> str | None:
    """One spelling everywhere, the regional table's when it knows the country ("Cote d'Ivoire" -> "Côte d'Ivoire")."""
    name = _blank(name)
    return COUNTRY_NAMES.get(country_code(name), name) if name else None


def pii_hit_types(entities: list[dict]) -> list[str]:
    return sorted({e["Type"] for e in entities if e["Type"] in PII_TYPES and e["Score"] >= PII_MIN_SCORE})


def _encode_entities(entities: list[dict]) -> str:
    return ";".join(sorted(f"{e['Type']}:{e['Score']:.4f}" for e in entities))


def _decode_entities(text: str) -> list[dict]:
    return [{"Type": t, "Score": float(s)} for t, s in (part.split(":") for part in text.split(";") if part)]


def read_inputs(inputs_dir: Path) -> dict:
    with open(inputs_dir / "producer_definitions.json", encoding="utf-8") as fh:
        definitions = json.load(fh)
    vocabulary: dict[str, dict[str, str]] = defaultdict(dict)
    for row in _read(inputs_dir / "vocabulary_map.csv"):
        vocabulary[row["field"]][normalize(row["sample_value"])] = row["value"]
    tags = {normalize(r["sub_category"]): r["tags"].split(";") for r in _read(inputs_dir / "subcategory_tags.csv")}
    pii = {r["sha256"]: _decode_entities(r["entities"]) for r in _read(inputs_dir / "pii_checks.csv")}
    return {"definitions": definitions, "vocabulary": vocabulary, "tags": tags, "pii": pii}


# ---------------------------------------------------------------------------------------------
# The generator
# ---------------------------------------------------------------------------------------------

def generate(sample_dir: Path = SAMPLE_DIR, inputs_dir: Path = INPUTS_DIR, pii_check: PiiCheck | None = None) -> dict:
    """Every output table, the report, and the PII check results (old plus any new).

    `pii_check` is called only for catalog descriptions with no result in pii_checks.csv. Without it (an
    offline run), a missing result raises MissingPiiCheck rather than skipping the check.
    """
    inputs = read_inputs(inputs_dir)
    report: dict = {"unmapped": defaultdict(Counter), "excluded_producers": [], "excluded_projects": [],
                    "projects_named_test": []}

    def mapped(field: str, value: str) -> str:
        found = inputs["vocabulary"][field].get(normalize(value))
        if found is None:
            report["unmapped"][field][value or "(blank)"] += 1
            return OTHER
        return found

    # Producers: FTUSA sample accounts with a crop in scope (not factories), then the synthetic ones.
    project_rows = _read(sample_dir / PROJECTS_FILE)
    regions: dict[str, Counter] = defaultdict(Counter)
    for row in project_rows:
        if row["region"]:  # the same values as country_region_name in the linked projects file
            regions[row["account_sk"]][row["region"]] += 1

    producers, certifications = [], []
    for account in _read(sample_dir / ACCOUNTS_FILE):
        pid, raw_crops = account["account_sk"], account["product_category_name"]
        if account["structure_txt"] == "Factory":
            report["excluded_producers"].append({"producer_id": pid, "reason": "factory"})
            continue
        crops = sorted({mapped("crop", c.strip()) for c in raw_crops.split(";") if c.strip()} or {OTHER})
        if not KEPT_CROPS & set(crops):
            report["excluded_producers"].append({"producer_id": pid, "reason": f"crop not in scope: {raw_crops or '(blank)'}"})
            continue
        counts = regions.get(pid)
        # Most projects decide the region; ties go to the alphabetically first.
        admin1 = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if counts else None
        producers.append({"producer_id": pid, "country": canonical_country(account["country_name"]), "admin1": admin1,
                          "crops": crops, "entity_type": mapped("entity_type", account["structure_txt"]),
                          "origin": "sample"})
        if _blank(account["certification_scope_name"]):
            certifications.append({"producer_id": pid, "certification_scope": account["certification_scope_name"].strip()})

    synthetic = inputs["definitions"]["producers"]
    for d in synthetic:
        producers.append({"producer_id": d["producer_id"], "country": d["country"], "admin1": d["admin1"],
                          "crops": sorted(d["crops"]), "entity_type": d["entity_type"], "origin": "synthetic"})
        if d.get("certification_scope"):
            certifications.append({"producer_id": d["producer_id"], "certification_scope": d["certification_scope"]})
    by_id = {p["producer_id"]: p for p in producers}

    # Premium projects. The project ID (producer table) and catalog ID (peer catalog) are separate hashes of
    # the same key, so one can't be linked to the other. The sample repeats a few projects word for word,
    # so repeats get an occurrence number.
    seen: Counter = Counter()

    def ids(*key: str) -> tuple[str, str]:
        n = seen[key]
        seen[key] += 1
        parts = (*key, str(n)) if n else key
        return _id("PRJ", "project", *parts), _id("CAT", "catalog", *parts)

    status_index = build_status_index(sample_dir / STATUS_FILE)
    projects, catalog_candidates = [], []
    for row in project_rows:
        pid = row["account_sk"]
        title, description = row["translated_project_name"], row["translated_project_description_txt"]
        project_id, catalog_id = ids(pid, title, description)
        if pid not in by_id:
            continue
        texts = (title, description, row["translated_project_reason_txt"], row["translated_primary_goal_txt"])
        if any(_PLACEHOLDER.search(t or "") for t in texts):
            report["excluded_projects"].append({"project_id": project_id, "title": title, "reason": "placeholder text"})
            continue
        start = resolve_status(status_index, row).get("project_start_date") or ""
        start_year = int(start[:4]) if start[:4].isdigit() and not start.startswith("1970-01-01") else None
        sub_category = _blank(row["subcategory"])
        tags = inputs["tags"].get(normalize(sub_category), [])
        if sub_category and not tags:
            report["unmapped"]["sub_category"][sub_category] += 1
        project = {"project_id": project_id, "producer_id": pid, "title": title, "category": _blank(row["category"]),
                   "sub_category": sub_category, "tags": tags, "start_year": start_year, "amount": None,
                   "description": description}
        projects.append(project)
        if "test" in normalize(title).split():
            report["projects_named_test"].append({"project_id": project_id, "producer_id": pid, "title": title})
        if not tags:
            report["excluded_projects"].append({"project_id": project_id, "title": title,
                                                "reason": f"sub-category not mapped: {sub_category or '(blank)'}"})
            continue
        catalog_candidates.append((project, catalog_id, canonical_country(row["country"])))

    for d in synthetic:
        for p in d["projects"]:
            project_id, catalog_id = ids(d["producer_id"], p["title"], p["description"])
            project = {"project_id": project_id, "producer_id": d["producer_id"], "title": p["title"],
                       "category": p.get("category"), "sub_category": p.get("sub_category"), "tags": p["tags"],
                       "start_year": p.get("start_year"), "amount": p.get("amount"), "description": p["description"]}
            projects.append(project)
            catalog_candidates.append((project, catalog_id, d["country"]))

    # Peer catalog: publishable fields, plus catalog_id, tags and the private owner_producer_id (#7, #16).
    pii_results = dict(inputs["pii"])
    pii_report = {"checked": 0, "hits": 0, "address_only_hits": 0}
    new_checks = 0
    names = fictional_names([project["producer_id"] for project, _, _ in catalog_candidates])
    catalog = []
    for project, catalog_id, country in catalog_candidates:
        owner = by_id[project["producer_id"]]
        description = _short(fictionalize(project["description"] or project["title"]))
        key = _sha256(description)
        if key not in pii_results:
            if pii_check is None:
                raise MissingPiiCheck(f"no PII check result for {project['project_id']} ({project['title']!r}); "
                                      "run without --offline, with AWS credentials")
            pii_results[key] = [{"Type": e["Type"], "Score": e["Score"]} for e in pii_check(description)]
            new_checks += 1
        pii_report["checked"] += 1
        hits = pii_hit_types(pii_results[key])
        if hits:
            pii_report["hits"] += 1
            pii_report["address_only_hits"] += hits == ["ADDRESS"]
            report["excluded_projects"].append({"project_id": project["project_id"], "title": project["title"],
                                                "reason": f"PII hit: {', '.join(hits)}"})
            continue
        catalog.append({"catalog_id": catalog_id, "organization": names[owner["producer_id"]], "country": country,
                        "crop": ";".join(owner["crops"]), "entity_type": owner["entity_type"],
                        "category": project["category"], "sub_category": project["sub_category"],
                        "start_year": project["start_year"], "description": description, "tags": project["tags"],
                        "owner_producer_id": owner["producer_id"]})

    surveys = _sample_surveys(sample_dir, by_id) + _synthetic_surveys(synthetic)

    report.update({
        "producers": {"total": len(producers), "by_origin": dict(Counter(p["origin"] for p in producers)),
                      "by_country": dict(Counter(p["country"] or "(blank)" for p in producers)),
                      "by_crop": dict(Counter(c for p in producers for c in p["crops"])),
                      "by_entity_type": dict(Counter(p["entity_type"] for p in producers))},
        "premium_projects": len(projects), "peer_catalog": len(catalog), "survey_responses": len(surveys),
        "certifications": len(certifications), "pii": pii_report,
        "unmapped": {field: dict(counts) for field, counts in sorted(report["unmapped"].items())},
    })
    return {
        "producers": sorted(producers, key=lambda p: p["producer_id"]),
        "premium_projects": sorted(projects, key=lambda p: p["project_id"]),
        "survey_responses": sorted(surveys, key=lambda r: r["survey_response_id"]),
        "certifications": sorted(certifications, key=lambda c: c["producer_id"]),
        "peer_catalog": sorted(catalog, key=lambda c: c["catalog_id"]),
        "report": _sorted_report(report),
        "pii_checks": pii_results,
        "new_pii_checks": new_checks,  # not in the report, so the report does not depend on the run
    }


def _survey_row(producer_id: str, response_id: str, year: int | None) -> dict:
    return {"producer_id": producer_id, "survey_response_id": response_id, "response_year": year,
            **{c: None for c in SURVEY_COLUMNS}, **{q: [] for q in MULTI_FIELDS}}


def _sample_surveys(sample_dir: Path, producers: dict) -> list[dict]:
    """Allowlisted columns only, for producers in the producer table. Nothing else is copied."""
    rows: dict[str, dict] = {}
    for r in _read(sample_dir / SINGLE_FILE):
        if r["account_sk"] not in producers or r["survey_response_sk"] in rows:
            continue
        date = r["response_date"] or ""
        row = _survey_row(r["account_sk"], r["survey_response_sk"], int(date[:4]) if date[:4].isdigit() else None)
        for c in SURVEY_COLUMNS:
            row[c] = _number(r[c]) if c in NUMBER_FIELDS else _blank(r[c])
        rows[r["survey_response_sk"]] = row
    header = {h["survey_response_sk"]: h["recorded_date"] or h["end_date"] or h["start_date"] or ""
              for h in _read(sample_dir / HEADER_FILE)}
    for r in _read(sample_dir / MULTI_FILE):
        if r["account_sk"] not in producers or r["question_label_txt"] not in MULTI_FIELDS:
            continue
        rid = r["survey_response_sk"]
        if rid not in rows:
            date = header.get(rid, "")
            rows[rid] = _survey_row(r["account_sk"], rid, int(date[:4]) if date[:4].isdigit() else None)
        choice = _blank(r["question_choice_txt"])
        if choice and choice not in rows[rid][r["question_label_txt"]]:
            rows[rid][r["question_label_txt"]].append(choice)
    for row in rows.values():
        for q in MULTI_FIELDS:
            row[q].sort()
    return list(rows.values())


def _synthetic_surveys(synthetic: list[dict]) -> list[dict]:
    rows = []
    for d in synthetic:
        for n, answers in enumerate(d.get("survey_responses", []), start=1):
            unknown = set(answers) - set(SURVEY_COLUMNS) - set(MULTI_FIELDS) - {"response_year"}
            if unknown:
                raise ValueError(f"{d['producer_id']}: survey columns outside the #14 allowlist: {sorted(unknown)}")
            row = _survey_row(d["producer_id"], f"{d['producer_id']}-SR-{n:02d}", answers.get("response_year"))
            row.update({k: v for k, v in answers.items() if k != "response_year"})
            for q in MULTI_FIELDS:
                row[q] = sorted(row[q])
            rows.append(row)
    return rows


def _sorted_report(report: dict) -> dict:
    report["excluded_producers"].sort(key=lambda r: r["producer_id"])
    report["excluded_projects"].sort(key=lambda r: (r["reason"], r["project_id"]))
    report["projects_named_test"].sort(key=lambda r: r["project_id"])
    return report


# ---------------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------------

def _jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def write(outputs: dict, root: Path = GENERATED_DIR, inputs_dir: Path = INPUTS_DIR) -> None:
    for name in TABLES:
        path = table_path(name, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_jsonl(outputs[name]), encoding="utf-8", newline="\n")
    (root / "report.json").write_text(json.dumps(outputs["report"], indent=1, ensure_ascii=False) + "\n",
                                      encoding="utf-8", newline="\n")
    with open(inputs_dir / "pii_checks.csv", "w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh, lineterminator="\n")
        out.writerow(["sha256", "entities"])
        for key in sorted(outputs["pii_checks"]):
            out.writerow([key, _encode_entities(outputs["pii_checks"][key])])


def comprehend_check() -> PiiCheck:  # pragma: no cover - needs AWS
    import boto3  # in the "generator" dependency group: tests and the agent never call Comprehend

    client = boto3.client("comprehend")
    return lambda text: client.detect_pii_entities(Text=text, LanguageCode="en")["Entities"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true",
                        help="never call Comprehend; fail if a catalog description has no PII check result")
    args = parser.parse_args(argv)
    outputs = generate(pii_check=None if args.offline else comprehend_check())
    write(outputs)
    r = outputs["report"]
    print(f"wrote {GENERATED_DIR}: {r['producers']['total']} producers ({r['producers']['by_origin']}), "
          f"{r['premium_projects']} projects, {r['peer_catalog']} catalog rows, {r['survey_responses']} survey "
          f"responses, {r['certifications']} certifications; PII {r['pii']}, "
          f"{outputs['new_pii_checks']} new Comprehend checks", file=sys.stderr)


if __name__ == "__main__":
    main()
