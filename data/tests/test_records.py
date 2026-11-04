"""Producer records (#14): own profile, projects and a safe survey summary."""
import json

from fx_data.records import (ALLOWED_FIELDS, MIN_RESPONSES, RECORDS_PATH, _survey_facts,
                             build_records)


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
    assert len(facts) == 1 and facts[0]["respondents"] == MIN_RESPONSES


def test_non_answers_are_left_out_of_shares():
    rows = [{f: "" for f in ALLOWED_FIELDS} | {"response_date": "2024-01-01"} for _ in range(8)]
    for r, answer in zip(rows, ["Yes"] * 3 + ["No"] * 2 + ["Refused", "Don't Know", ""]):
        r["has_soil_conservation_practices_code"] = answer
    assert _survey_facts(rows, [])[0]["text"].startswith("60% of 5 surveyed households")


def test_producers_without_surveys_get_a_note():
    for r in build_records()["records"].values():
        if not r["survey"]["facts"]:
            assert r["survey"]["note"]
