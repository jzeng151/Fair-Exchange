"""The producer data generator (#7 spec): fixture sample with the Comprehend step stubbed, then the committed files."""
import csv
import json
import shutil
from pathlib import Path

import pytest
from fx_data.generator import (ACCOUNTS_FILE, HEADER_FILE, INPUTS_DIR, MULTI_FILE, PROJECTS_FILE, SINGLE_FILE,
                               STATUS_FILE, MissingPiiCheck, generate, write)
from fx_data.peers import PUBLISHABLE, SAMPLE_DIR, PeerProjects, ProducerProfiles, crop_set
from fx_data.records import ALLOWED_FIELDS, MULTI_FIELDS
from fx_data.tables import GENERATED_DIR, TABLES, read_table, table_path

# ---------------------------------------------------------------------------------------------
# Fixture sample: a few rows that each exercise one rule
# ---------------------------------------------------------------------------------------------

ACCOUNTS = [  # account_sk, product_category_name, structure_txt, country_name, certification_scope_name
    ("COOP", "Coffee", "1st Grade", "Colombia", "Producer"),
    ("IVOIRE", "Cocoa;Coffee", "", "Cote d'Ivoire", ""),
    ("TIE", "Bananas", "Mystery Grade", "Ecuador", "Producer"),
    ("FACTORY", "Apparel", "Factory", "Vietnam", "Producer"),
    ("APPAREL", "Apparel;Denim", "", "India", "Producer"),
    ("TEA", "Tea", "Estate", "Kenya", "Producer"),
]
PROJECTS = [  # account, name, description, region, sub-category, start date
    ("COOP", "Tanks", "Rainwater tanks for the mill.", "Huila", "Clean Water", "2022-01-01"),
    ("COOP", "Tanks", "Rainwater tanks for the mill.", "Huila", "Clean Water", "2022-01-01"),  # a repeat
    ("COOP", "Solar", "Solar dryer.", "Cauca", "", "2023-01-01"),
    ("COOP", "Office", "New office chairs.", "Huila", "Furniture Upgrades", "2023-01-01"),
    ("COOP", "Maria's well", "Maria Lopez dug a well.", "Huila", "Clean Water", "2024-01-01"),
    ("COOP", "Dated", "Started in March 2021.", "Huila", "Clean Water", "2021-03-01"),
    ("TIE", "Lorem", "Lorem ipsum dolor sit amet.", "Zeta", "Clean Water", "2022-01-01"),
    ("TIE", "Beta work", "Diversify crops.", "Beta", "Crop Diversification", "2022-01-01"),
    ("TIE", "Alpha work", "Plant trees.", "Alpha", "Sustainability efforts", "1970-01-01"),
    ("FACTORY", "Factory roof", "A new roof.", "Binh Duong", "Clean Water", "2022-01-01"),
]
SENSITIVE = "SENSITIVE-ANSWER"
DEFINITIONS = {"producers": [{
    "producer_id": "SYN-001", "country": "Peru", "admin1": "Junin", "crops": ["coffee"], "entity_type": "smallholder",
    "certification_scope": "Producer",
    "projects": [{"title": "Shared crews", "category": "Social", "sub_category": None, "tags": ["labor and migration"],
                  "start_year": 2024, "amount": 500, "description": "Shared picker crews."}],
    "survey_responses": [{"response_year": 2024, "has_hired_labor_code": "Yes", "income_sources_ms_core": ["Corn"]}],
}], "contrast_pairs": []}

# Comprehend answers for the stub, by description
PII = {"Maria Lopez dug a well.": [{"Type": "NAME", "Score": 0.95}],
       "Started in March 2021.": [{"Type": "DATE_TIME", "Score": 0.99}, {"Type": "NAME", "Score": 0.79999}]}  # just under the threshold


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        out = csv.DictWriter(fh, header)
        out.writeheader()
        out.writerows(rows)


def _real_header(file: Path) -> list[str]:
    with open(SAMPLE_DIR / file, encoding="utf-8") as fh:
        return next(csv.reader(fh))


@pytest.fixture
def sample(tmp_path) -> Path:
    root = tmp_path / "sample"
    _write_csv(root / ACCOUNTS_FILE, _real_header(ACCOUNTS_FILE), [
        {"account_sk": a, "product_category_name": c, "structure_txt": s, "country_name": k,
         "certification_scope_name": scope, "certification_status_name": "Authorized"}
        for a, c, s, k, scope in ACCOUNTS])
    _write_csv(root / PROJECTS_FILE, _real_header(PROJECTS_FILE), [
        {"account_sk": a, "translated_project_name": n, "translated_project_description_txt": d, "region": r,
         "subcategory": sub, "category": "Environmental", "country": "Colombia"} for a, n, d, r, sub, _ in PROJECTS])
    _write_csv(root / STATUS_FILE, _real_header(STATUS_FILE), [
        {"account_sk": a, "project_name": n, "project_description_txt": d, "country_region_name": r,
         "sub_category_taxonomy_term_txt": sub, "project_start_date": start, "project_status_name": "Completed"}
        for a, n, d, r, sub, start in PROJECTS])
    single = _real_header(SINGLE_FILE)
    _write_csv(root / SINGLE_FILE, single, [  # every column filled, the sensitive ones too
        {c: "Yes" if c in ALLOWED_FIELDS else SENSITIVE for c in single} | {"survey_response_sk": "R1", "account_sk": "COOP", "response_date": "2024-05-01",
                                          "farm_area_ha_nbr": "2.5", "yield_produced_per_hectare_nbr": "0.000000",
                                          "has_hired_labor_code": "Yes"},
        {c: "x" for c in single} | {"survey_response_sk": "R9", "account_sk": "FACTORY", "response_date": "2024-05-01"}])
    _write_csv(root / MULTI_FILE, _real_header(MULTI_FILE), [
        {"survey_response_sk": "R1", "account_sk": "COOP", "question_label_txt": "harvest_change_reason_core",
         "question_choice_txt": "Climate change"},
        {"survey_response_sk": "R1", "account_sk": "COOP", "question_label_txt": "borrowing_ms_core",
         "question_choice_txt": SENSITIVE},
        {"survey_response_sk": "R2", "account_sk": "COOP", "question_label_txt": "ft_benefits_ms_core",
         "question_choice_txt": "Training"}])
    _write_csv(root / HEADER_FILE, _real_header(HEADER_FILE), [
        {"survey_response_sk": "R2", "recorded_date": "2023-02-01"}])
    return root


@pytest.fixture
def inputs(tmp_path) -> Path:
    root = tmp_path / "inputs"
    root.mkdir()
    for name in ("vocabulary_map.csv", "subcategory_tags.csv"):
        shutil.copy(INPUTS_DIR / name, root / name)
    (root / "producer_definitions.json").write_text(json.dumps(DEFINITIONS), encoding="utf-8")
    (root / "pii_checks.csv").write_text("sha256,entities\n", encoding="utf-8")
    return root


class Comprehend:
    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, text: str) -> list[dict]:
        self.calls.append(text)
        return PII.get(text, [])


@pytest.fixture
def out(sample, inputs) -> dict:
    return generate(sample, inputs, Comprehend())


def _producer(out, pid):
    return next((p for p in out["producers"] if p["producer_id"] == pid), None)


def _catalog_titles(out) -> set[str]:
    descriptions = {c["description"] for c in out["peer_catalog"]}
    return {p["title"] for p in out["premium_projects"] if p["description"] in descriptions}


# ---------------------------------------------------------------------------------------------
# Spec 07 testing decisions, on the fixture sample
# ---------------------------------------------------------------------------------------------

def test_same_inputs_give_byte_identical_files(sample, inputs, tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    write(generate(sample, inputs, Comprehend()), first, inputs)
    write(generate(sample, inputs, None), second, inputs)  # second run: every PII result is in the file
    for path in [*(table_path(name, first) for name in TABLES), first / "report.json"]:
        assert path.read_bytes() == (second / path.relative_to(first)).read_bytes(), path.name


def test_factories_and_out_of_scope_crops_are_left_out_and_reported(out):
    ids = {p["producer_id"] for p in out["producers"]}
    assert ids == {"COOP", "IVOIRE", "TIE", "SYN-001"}
    reasons = {r["producer_id"]: r["reason"] for r in out["report"]["excluded_producers"]}
    assert reasons["FACTORY"] == "factory"
    assert reasons["APPAREL"].startswith("crop not in scope") and reasons["TEA"].startswith("crop not in scope")
    text = json.dumps({k: out[k] for k in TABLES})
    assert "FACTORY" not in text and "Factory roof" not in text and "R9" not in text


def test_sample_values_map_to_the_vocabulary_and_unmapped_values_are_reported(out):
    assert _producer(out, "COOP")["entity_type"] == "cooperative"
    assert _producer(out, "IVOIRE")["crops"] == ["cocoa", "coffee"]
    assert _producer(out, "IVOIRE")["entity_type"] == "other"
    assert _producer(out, "TIE")["crops"] == ["banana"] and _producer(out, "TIE")["entity_type"] == "other"
    unmapped = out["report"]["unmapped"]
    assert unmapped["entity_type"] == {"(blank)": 1, "Mystery Grade": 1}
    assert {"Apparel", "Denim", "Tea"} <= set(unmapped["crop"])
    assert unmapped["sub_category"] == {"Furniture Upgrades": 1}


def test_one_country_spelling(out):
    assert _producer(out, "IVOIRE")["country"] == "Côte d'Ivoire"


def test_region_comes_from_the_producers_projects(out):
    assert _producer(out, "COOP")["admin1"] == "Huila"  # most projects
    assert _producer(out, "TIE")["admin1"] == "Alpha"  # a 3-way tie goes to the alphabetically first
    assert _producer(out, "IVOIRE")["admin1"] is None  # no projects


def test_survey_holds_only_allowlisted_columns_even_when_every_column_is_filled(out):
    expected = {"producer_id", "survey_response_id", "response_year"} | ALLOWED_FIELDS | set(MULTI_FIELDS)
    rows = {r["survey_response_id"]: r for r in out["survey_responses"]}
    assert set(rows) == {"R1", "R2", "SYN-001-SR-01"}
    for r in rows.values():
        assert set(r) == expected
    assert SENSITIVE not in json.dumps(out)
    r1 = rows["R1"]
    assert r1["farm_area_ha_nbr"] == 2.5 and r1["has_hired_labor_code"] == "Yes" and r1["response_year"] == 2024
    assert r1["harvest_change_reason_core"] == ["Climate change"]
    assert rows["R2"]["response_year"] == 2023 and rows["R2"]["ft_benefits_ms_core"] == ["Training"]


def test_certification_holds_scope_only(out):
    assert out["certifications"] == [{"producer_id": "COOP", "certification_scope": "Producer"},
                                     {"producer_id": "SYN-001", "certification_scope": "Producer"},
                                     {"producer_id": "TIE", "certification_scope": "Producer"}]
    assert "Authorized" not in json.dumps(out)


def test_repeated_projects_get_their_own_ids_and_catalog_ids_are_not_project_ids(out):
    project_ids = [p["project_id"] for p in out["premium_projects"]]
    catalog_ids = [c["catalog_id"] for c in out["peer_catalog"]]
    assert len(project_ids) == len(set(project_ids)) and len(catalog_ids) == len(set(catalog_ids))
    assert sum(p["title"] == "Tanks" for p in out["premium_projects"]) == 2
    assert not {i[4:] for i in project_ids} & {i[4:] for i in catalog_ids}


def test_catalog_holds_only_publishable_fields_plus_id_tags_and_owner(out):
    accounts = {a for a, *_ in ACCOUNTS}
    project_ids = {p["project_id"] for p in out["premium_projects"]}
    for row in out["peer_catalog"]:
        assert set(row) == set(PUBLISHABLE) | {"catalog_id", "tags", "owner_producer_id"}
        public = json.dumps({k: v for k, v in row.items() if k != "owner_producer_id"})
        assert not [a for a in accounts if a in public] and not [p for p in project_ids if p in public]


def test_unmapped_or_blank_sub_categories_and_placeholders_stay_out_of_the_catalog(out):
    titles = _catalog_titles(out)
    assert {"Solar", "Office", "Lorem"}.isdisjoint(titles)
    reasons = {r["title"]: r["reason"] for r in out["report"]["excluded_projects"]}
    assert reasons["Solar"] == "sub-category not mapped: (blank)"
    assert reasons["Office"] == "sub-category not mapped: Furniture Upgrades"
    assert reasons["Lorem"] == "placeholder text"
    # The producer's own record keeps the unmapped projects, with no tags.
    assert {p["title"]: p["tags"] for p in out["premium_projects"]}["Solar"] == []


def test_a_pii_hit_leaves_the_project_out_but_dates_and_low_scores_do_not(out):
    titles = _catalog_titles(out)
    assert "Maria's well" not in titles and "Dated" in titles
    reasons = {r["title"]: r["reason"] for r in out["report"]["excluded_projects"]}
    assert reasons["Maria's well"] == "PII hit: NAME"
    assert out["report"]["pii"]["hits"] == 1


def test_descriptions_already_checked_are_not_sent_to_comprehend(sample, inputs):
    write(generate(sample, inputs, Comprehend()), inputs.parent / "out", inputs)
    again = Comprehend()
    generate(sample, inputs, again)
    assert again.calls == []


def test_an_offline_run_with_a_missing_check_fails(sample, inputs):
    with pytest.raises(MissingPiiCheck):
        generate(sample, inputs, None)


def test_a_synthetic_survey_column_outside_the_allowlist_fails(sample, inputs):
    bad = json.loads(json.dumps(DEFINITIONS))
    bad["producers"][0]["survey_responses"][0]["red_pesticide_code"] = "Yes"
    (inputs / "producer_definitions.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist"):
        generate(sample, inputs, Comprehend())


def test_the_peer_tool_leaves_out_a_sample_producers_own_projects(out):
    catalog = PeerProjects({"projects": out["peer_catalog"]})
    items = catalog.find("COOP", {"water", "market and price", "biodiversity and conservation", "labor and migration"},
                         {"coffee"}, "cooperative")
    assert items, "the fixture has other producers' projects"
    own = {c["catalog_id"] for c in out["peer_catalog"] if c["owner_producer_id"] == "COOP"}
    text = json.dumps(items)
    assert not [i for i in items if i["source"].rsplit("[", 1)[1].rstrip("]") in own]
    assert "owner_producer_id" not in text and "COOP" not in text and "TIE" not in text


# ---------------------------------------------------------------------------------------------
# The committed files
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def committed() -> dict:
    return {name: read_table(name) for name in TABLES} | {
        "report": json.loads((GENERATED_DIR / "report.json").read_text(encoding="utf-8"))}


@pytest.fixture(scope="module")
def definitions() -> dict:
    return json.loads((INPUTS_DIR / "producer_definitions.json").read_text(encoding="utf-8"))


def test_committed_files_match_the_inputs(committed):
    # Offline: every catalog description has a committed PII check result.
    fresh = generate(pii_check=None)
    for name in (*TABLES, "report"):
        assert fresh[name] == committed[name], f"{name} is stale: run python -m fx_data.generator"


def _profile(committed, pid) -> dict:
    return next(p for p in committed["producers"] if p["producer_id"] == pid)


@pytest.mark.parametrize("pid, country, admin1, crops, entity_type", [
    ("SYN-001", "Colombia", "Cauca", ["coffee"], "smallholder"),       # S1 drought
    ("SYN-002", "Mexico", "Chiapas", ["coffee"], "cooperative"),       # S2 price drop
    ("SYN-003", "Vietnam", "Dak Lak", ["coffee"], "processor"),        # S3 labor shortage
    ("SYN-004", "Honduras", "Copan", ["coffee"], "cooperative"),       # S4 Spanish-language producer
    ("SYN-005", "Côte d'Ivoire", "Bas-Sassandra", ["cocoa"], "cooperative"),  # S5
    ("SYN-006", "Côte d'Ivoire", "Goh-Djiboua", ["cocoa"], "smallholder"),
])
def test_scenario_producers_exist_with_their_profiles(committed, pid, country, admin1, crops, entity_type):
    assert _profile(committed, pid) == {"producer_id": pid, "country": country, "admin1": admin1, "crops": crops,
                                        "entity_type": entity_type, "origin": "synthetic"}


def test_scenario_producers_have_projects_with_their_challenge(committed):
    tags = {}
    for p in committed["premium_projects"]:
        tags.setdefault(p["producer_id"], set()).update(p["tags"])
    assert "climate and weather" in tags["SYN-001"] and "market and price" in tags["SYN-002"]
    assert "labor and migration" in tags["SYN-003"]


def test_scope_producers_differ_in_country_region_and_crop(committed):
    a, b = _profile(committed, "SYN-SCOPE-A"), _profile(committed, "SYN-SCOPE-B")
    assert a["country"] != b["country"] and a["admin1"] != b["admin1"] and not set(a["crops"]) & set(b["crops"])


def test_priority_countries_and_crops_are_covered(committed):
    countries = {p["country"] for p in committed["producers"]}
    crops = {c for p in committed["producers"] for c in p["crops"]}
    assert {"Peru", "Côte d'Ivoire", "Colombia", "Honduras", "Mexico"} <= countries
    assert {"coffee", "banana", "cocoa"} <= crops
    assert sum(p["country"] == "Côte d'Ivoire" and "cocoa" in p["crops"] for p in committed["producers"]) >= 2


ATTRIBUTES = {"crop": lambda p: set(p["crops"]), "region": lambda p: (p["country"], p["admin1"]),
              "entity_type": lambda p: p["entity_type"]}


def test_contrast_pairs_share_a_tag_and_differ_as_declared(committed, definitions):
    pairs = definitions["contrast_pairs"]
    assert len(pairs) >= 3
    tags = {}
    for p in committed["premium_projects"]:
        tags.setdefault(p["producer_id"], set()).update(p["tags"])
    for pair in pairs:
        a, b = (_profile(committed, pid) for pid in pair["producers"])
        assert pair["tag"] in tags[a["producer_id"]] & tags[b["producer_id"]], pair["pair_id"]
        for name, value in ATTRIBUTES.items():
            assert (value(a) != value(b)) == (name in pair["differ_in"]), (pair["pair_id"], name)


def test_contrast_pairs_get_different_peer_examples_from_the_same_candidates(committed, definitions):
    # The vision's "distinct responses" metric: the same candidate pool for both producers (neither one's own
    # projects), so a difference comes from ranking on crop and entity type, not from own-project exclusion.
    profiles = ProducerProfiles.load()
    for pair in definitions["contrast_pairs"]:
        pool = PeerProjects({"projects": [c for c in committed["peer_catalog"]
                                          if c["owner_producer_id"] not in pair["producers"]]})
        results = []
        for pid in pair["producers"]:
            p = profiles.get(pid)
            items = pool.find("nobody", {pair["tag"]}, crop_set(p.crop), p.entity_type)
            assert items, (pair["pair_id"], pid)
            results.append([(i["source"], i["strength"]) for i in items])
        assert results[0] != results[1], pair["pair_id"]
