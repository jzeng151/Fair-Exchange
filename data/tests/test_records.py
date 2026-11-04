"""Producer records (#14): own profile, projects and a safe survey summary."""
import json

from fx_data.records import (ALLOWED_FIELDS, MIN_RESPONSES, RECORDS_PATH, _survey_facts,
                             build_records)
from fx_data.peers import PEERS_PATH, _PLACEHOLDER


def test_committed_records_match_the_sample_data():
    assert json.loads(RECORDS_PATH.read_text(encoding="utf-8")) == build_records()


def test_every_producer_has_a_record_with_a_cited_profile():
    records = build_records()["records"]
    assert len(records) == 146
    assert all(r["profile"]["source"] and r["profile"]["country"] for r in records.values())


def test_only_allowlisted_survey_fields_are_read():
    sensitive = {"sexual", "harass", "borrow", "med_", "child", "income", "committee", "leadership",
                 "covid", "unsafe", "report"}
    assert not {f for f in ALLOWED_FIELDS if any(s in f for s in sensitive)}


def test_shares_need_at_least_min_responses():
    rows = [{f: "" for f in ALLOWED_FIELDS} | {"response_date": "2024-01-01"} for _ in range(MIN_RESPONSES - 1)]
    for r in rows:
        r["has_soil_conservation_practices_code"] = "Yes"
    assert _survey_facts(rows, []) == []
    rows.append(dict(rows[0]))
    facts = _survey_facts(rows, [])
    assert len(facts) == 1 and facts[0]["responses"] == MIN_RESPONSES


def test_non_answers_are_left_out_of_shares():
    rows = [{f: "" for f in ALLOWED_FIELDS} | {"response_date": "2024-01-01"} for _ in range(8)]
    for r, answer in zip(rows, ["Yes"] * 3 + ["No"] * 2 + ["Refused", "Don't Know", ""]):
        r["has_soil_conservation_practices_code"] = answer
    assert _survey_facts(rows, [])[0]["text"].startswith("60% of 5 survey responses say they")


def test_producers_without_surveys_get_a_note():
    for r in build_records()["records"].values():
        if not r["survey"]["facts"]:
            assert r["survey"]["note"]


# ---- Regression tests for the code-review findings on #62 --------------------------------------

def _response_row(**answers) -> dict:
    return {f: "" for f in ALLOWED_FIELDS} | {"response_date": "2024-01-01", "response": "r"} | answers


def _reasons(*pairs: tuple[str, str], date: str = "2024-03-01") -> list[dict]:
    """(response id, reason) pairs, one per selection."""
    return [{"response": r, "choice": c, "date": date} for r, c in pairs]


def test_multiple_choice_counts_distinct_responses_not_selections():
    # Five selections made by only two responses: below the minimum, so nothing is published.
    picks = _reasons(("r1", "Climate change"), ("r1", "Old trees"), ("r1", "Pests"),
                     ("r2", "Climate change"), ("r2", "Old trees"))
    assert len(picks) == MIN_RESPONSES
    assert _survey_facts([], picks) == []


def test_multiple_choice_reports_distinct_responses_and_names_only_well_supported_reasons():
    picks = _reasons(*[(f"r{i}", "Climate change") for i in range(6)],
                     *[(f"r{i}", "Old trees") for i in range(2)])  # two responses also chose this
    (fact,) = _survey_facts([], picks)
    assert fact["responses"] == 6  # distinct responses, although there are 8 selections
    assert "Climate change (6 responses)" in fact["text"]
    assert "Old trees" not in fact["text"]  # only 2 responses: too few to name


def test_multiple_choice_ignores_other_and_non_answers():
    picks = _reasons(*[(f"r{i}", "Other") for i in range(8)], *[(f"s{i}", "Refused") for i in range(8)])
    assert _survey_facts([], picks) == []


def test_each_fact_gets_the_period_of_its_own_responses():
    rows = [_response_row(response_date="2025-02-01", has_water_conservation_practices_code="Yes") for _ in range(5)] + \
           [_response_row(response_date="2021-02-01", has_soil_conservation_practices_code="Yes") for _ in range(5)]
    facts = {f["text"].split(" say they ")[1]: f["period"] for f in _survey_facts(rows, [])}
    assert facts["use water conservation practices."] == "2025"
    assert facts["use soil conservation practices."] == "2021"


def test_multiple_choice_period_comes_from_the_responses_that_gave_the_reasons():
    picks = _reasons(*[(f"r{i}", "Climate change") for i in range(5)], date="2023-06-01")
    (fact,) = _survey_facts([_response_row(response_date="2020-01-01")], picks)
    assert fact["period"] == "2023"


def test_shipped_records_have_no_placeholder_projects():
    for r in build_records()["records"].values():
        for p in r["premium_projects"]:
            assert not _PLACEHOLDER.search(" ".join([p["name"], p["action"], p["challenge"], p["intended_outcome"]]))


def test_project_refs_are_unique_and_match_the_peer_table():
    refs = [p["project_ref"] for r in build_records()["records"].values() for p in r["premium_projects"]]
    assert len(refs) == len(set(refs))
    peer_refs = {p["catalog_id"] for p in json.loads(PEERS_PATH.read_text(encoding="utf-8"))["projects"]}
    assert set(refs) == peer_refs


def test_shipped_survey_facts_respect_the_minimum_and_never_say_households():
    for r in build_records()["records"].values():
        for f in r["survey"]["facts"]:
            assert f["responses"] >= MIN_RESPONSES
            assert "household" not in f["text"].lower()


# ---- #14 spec: certification status is never read; excluded survey columns stay excluded --------

def test_certification_status_is_never_returned():
    for r in build_records()["records"].values():
        assert "certification_status" not in r["profile"]
        assert "certification_status" not in json.dumps(r)
    assert "certification_status" not in RECORDS_PATH.read_text(encoding="utf-8")


def test_spec_excluded_columns_are_not_in_the_allowlist():
    excluded = {"coverted_natural_land_to_cropland_code", "hectare_natural_land_converted_nbr",
                "red_pesticide_code", "running_water_code", "water_access_distance_name",
                "non_drinking_water_sources_name", "non_drinking_water_condition_name",
                "drinking_water_treatment_method_name", "has_water_treatment_plant_code"}
    assert not ALLOWED_FIELDS & excluded

