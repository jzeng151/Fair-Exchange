"""Producer-record tool (#14), called through Strands so the session context is injected for real."""
import json

from fx_data.records import ProducerRecords

from fex.tools.producer_record import get_producer_record
from tests.tool_harness import call_tool

LOADED = ProducerRecords.load()
RECORDS = LOADED._records
WITH_SURVEY = next(pid for pid, r in RECORDS.items() if r["survey"]["facts"])
NO_SURVEY = next(pid for pid, r in RECORDS.items() if r["survey"]["responses"] == 0)


def _call(pid, tool_input=None):
    status, items = call_tool(get_producer_record, tool_input or {}, {"producer_id": pid})
    assert status == "success"
    return items


def test_model_cannot_set_any_parameter():
    assert get_producer_record.tool_spec["inputSchema"]["json"]["properties"] == {}


def test_returns_the_session_producers_certification_projects_and_survey_items():
    items = _call(WITH_SURVEY)
    assert items == LOADED.items(WITH_SURVEY)
    assert items[0]["source"] == f"Your certification record [{WITH_SURVEY}]"
    projects = [i for i in items if i["source"].startswith("Your Premium project: ")]
    assert len(projects) == len(RECORDS[WITH_SURVEY]["premium_projects"])
    assert all(set(p["data"]) == {"category", "sub_category", "year", "amount", "description"} for p in projects)
    assert any(" survey: " in i["source"] for i in items)


def test_items_follow_the_data_tool_contract():
    for pid in RECORDS:
        sources = [i["source"] for i in LOADED.items(pid)]
        assert len(sources) == len(set(sources)), pid  # unique per fact or record
        for item in LOADED.items(pid):
            assert set(item) == {"source", "kind", "text", "period", "strength", "data"}
            assert item["kind"] == "producer_record" and item["text"] and item["source"].endswith("]")


def test_a_producer_id_supplied_by_the_model_is_ignored():
    assert _call(WITH_SURVEY, {"producer_id": NO_SURVEY}) == _call(WITH_SURVEY)


def test_a_producer_without_surveys_gets_certification_and_projects_only():
    items = _call(NO_SURVEY)
    assert items and not any(" survey: " in i["source"] for i in items)


def test_no_sensitive_survey_topics_or_certification_status_are_returned():
    for pid in RECORDS:
        items = LOADED.items(pid)
        survey = json.dumps([i for i in items if " survey: " in i["source"]]).lower()
        # "income" is not listed: "I diversified my income sources" is an allowed fishing-adaptation answer.
        for word in ("harass", "discrim", "borrow", "loan", "medical", "child", "leadership", "committee"):
            assert word not in survey, (pid, word)
        fields = {k.lower() for i in items for k in i["data"]}
        assert not any("status" in f or "audit" in f for f in fields), pid
        assert "certification_status" not in json.dumps(items)


def test_unknown_producer_gets_an_empty_list():
    assert _call("NOT-A-PRODUCER") == []


def test_no_producer_in_session_is_refused():
    status, text = call_tool(get_producer_record, {}, {})
    assert status == "error" and "No producer in session" in text
