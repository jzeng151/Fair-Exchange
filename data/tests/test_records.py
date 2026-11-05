"""Producer records (#14): own certification scope, projects and a safe survey summary."""
import json

import pytest
from fx_data.peers import _PLACEHOLDER
from fx_data.records import (ALLOWED_FIELDS, MIN_RESPONSES, MULTI_FIELDS, ProducerRecords, _survey_facts,
                             build_records)
from fx_data.tables import read_table

RECORDS = build_records()


def _response(n=0, year=2024, **answers) -> dict:
    """One row of the survey table: every allowlisted column blank unless given."""
    return {"producer_id": "P", "survey_response_id": f"r{n}", "response_year": year,
            **{f: None for f in ALLOWED_FIELDS}, **{q: [] for q in MULTI_FIELDS}, **answers}


def _responses(count, **answers) -> list[dict]:
    return [_response(n, **answers) for n in range(count)]


def test_every_producer_in_the_table_has_a_record():
    assert set(RECORDS) == {p["producer_id"] for p in read_table("producers")}


def test_only_allowlisted_survey_fields_are_read():
    sensitive = {"sexual", "harass", "borrow", "med_", "child", "income", "committee", "leadership",
                 "covid", "unsafe", "report"}
    assert not {f for f in ALLOWED_FIELDS if any(s in f for s in sensitive)}


def test_the_allowlist_is_the_spec_list():
    # #14 spec, single-choice survey (besides the response year) and multiple-choice questions.
    assert ALLOWED_FIELDS == {
        "farm_area_ha_nbr", "has_hired_labor_code", "harvest_changed_code", "yield_produced_per_hectare_nbr",
        "has_integrated_pest_management_practices_name", "has_received_fertilizer_training_code",
        "has_forest_protection_practices_code", "has_water_conservation_practices_code",
        "has_water_contamination_prevention_practices_code", "has_soil_conservation_practices_code",
        "water_access_sources_name", "has_noticed_fishing_changes_code", "adaption_strategies_name",
        "future_concerns_name"}
    assert set(MULTI_FIELDS) == {"harvest_change_reason_core", "income_sources_ms_core", "ft_benefits_ms_core"}


def _value(field: str):
    return 2.0 if field.endswith("_nbr") else "Yes"


def test_every_allowlisted_question_gives_a_summary_at_the_minimum():
    # #14 spec: every single-choice column and all three multiple-choice questions, at 5 or more responses.
    rows = _responses(MIN_RESPONSES, **{f: _value(f) for f in ALLOWED_FIELDS},
                      **{q: ["Climate change"] for q in MULTI_FIELDS})
    assert {f["column"] for f in _survey_facts(rows)} == ALLOWED_FIELDS | set(MULTI_FIELDS)


def test_four_responses_give_nothing():
    rows = _responses(MIN_RESPONSES - 1, **{f: _value(f) for f in ALLOWED_FIELDS},
                      **{q: ["Climate change"] for q in MULTI_FIELDS})
    assert _survey_facts(rows) == []


def test_non_answers_are_left_out_of_shares():
    rows = [_response(n, has_soil_conservation_practices_code=a)
            for n, a in enumerate(["Yes"] * 3 + ["No"] * 2 + ["Refused", "Don't Know", None])]
    assert _survey_facts(rows)[0]["text"].startswith("60% of 5 survey responses say they")


def test_a_missing_number_is_recorded_as_zero_and_left_out():
    rows = _responses(4, farm_area_ha_nbr=2.0) + [_response(9, farm_area_ha_nbr=0.0)]
    assert _survey_facts(rows) == []
    (fact,) = _survey_facts(rows + [_response(10, farm_area_ha_nbr=3.0)])
    assert fact["responses"] == 5 and fact["text"].endswith(": 2.0.")


def test_multiple_choice_counts_distinct_responses_not_selections():
    # Five selections made by only two responses: below the minimum, so nothing is published.
    rows = [_response(1, harvest_change_reason_core=["Climate change", "Old trees", "Pests"]),
            _response(2, harvest_change_reason_core=["Climate change", "Old trees"])]
    assert _survey_facts(rows) == []


def test_multiple_choice_names_only_answers_five_responses_chose():
    rows = [_response(n, harvest_change_reason_core=["Climate change"] + (["Old trees"] if n < 2 else []))
            for n in range(6)]
    (fact,) = _survey_facts(rows)
    assert fact["responses"] == 6  # distinct responses, although there are 8 selections
    assert "Climate change (6 responses)" in fact["text"]
    assert "Old trees" not in fact["text"]  # only 2 responses: too few to name


def test_multiple_choice_with_no_well_supported_answer_names_none():
    rows = [_response(n, income_sources_ms_core=[f"Source {n}"]) for n in range(5)]
    (fact,) = _survey_facts(rows)
    assert "no single answer was given by 5 or more" in fact["text"]
    assert "Source" not in fact["text"]


def test_multiple_choice_ignores_other_and_non_answers():
    rows = [_response(n, ft_benefits_ms_core=["Other"]) for n in range(8)] + \
           [_response(n + 10, ft_benefits_ms_core=["Refused"]) for n in range(8)]
    assert _survey_facts(rows) == []


def test_each_fact_gets_the_period_of_its_own_responses():
    rows = [_response(n, 2025, has_water_conservation_practices_code="Yes") for n in range(5)] + \
           [_response(n + 5, 2021, has_soil_conservation_practices_code="Yes") for n in range(5)]
    facts = {f["text"].split(" say they ")[1]: f["period"] for f in _survey_facts(rows)}
    assert facts["use water conservation practices."] == "2025"
    assert facts["use soil conservation practices."] == "2021"


def test_shipped_records_have_no_placeholder_projects():
    for r in RECORDS.values():
        for p in r["premium_projects"]:
            assert not _PLACEHOLDER.search(" ".join([p["title"], p["description"]]))


def test_shipped_survey_facts_respect_the_minimum_and_never_say_households():
    for r in RECORDS.values():
        for f in r["survey"]["facts"]:
            assert f["responses"] >= MIN_RESPONSES
            assert "household" not in f["text"].lower()


def test_producers_without_surveys_get_a_note():
    for r in RECORDS.values():
        if not r["survey"]["facts"]:
            assert r["survey"]["note"]


@pytest.mark.parametrize("pid", ["SYN-001", "SYN-002", "SYN-003", "SYN-004", "SYN-005"])
def test_scenario_producers_have_survey_summaries_for_every_farming_question(pid):
    # #7: synthetic producers fill every summarized farming question, so the record tool shows them.
    columns = {f["column"] for f in RECORDS[pid]["survey"]["facts"]}
    farming = ALLOWED_FIELDS - {"has_noticed_fishing_changes_code", "adaption_strategies_name", "future_concerns_name"}
    assert columns == farming | set(MULTI_FIELDS)


def test_no_survey_response_id_appears_in_any_item():
    # #14 spec: summaries are cited by an opaque summary ID, never a survey response ID.
    records = ProducerRecords(RECORDS)
    response_ids = {r["survey_response_id"] for r in read_table("survey_responses")}
    for pid, r in RECORDS.items():
        if r["survey"]["responses"]:
            text = json.dumps(records.items(pid))
            assert not [rid for rid in response_ids if rid in text], pid


# ---- #14 spec: certification status is never read; excluded survey columns stay excluded --------

def test_certification_status_is_never_returned():
    for r in RECORDS.values():
        assert "certification_status" not in json.dumps(r)


def test_spec_excluded_columns_are_not_in_the_allowlist():
    excluded = {"coverted_natural_land_to_cropland_code", "hectare_natural_land_converted_nbr",
                "red_pesticide_code", "running_water_code", "water_access_distance_name",
                "non_drinking_water_sources_name", "non_drinking_water_condition_name",
                "drinking_water_treatment_method_name", "has_water_treatment_plant_code"}
    assert not ALLOWED_FIELDS & excluded
