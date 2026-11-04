"""Producer-record tool (#14), called through Strands so the session context is injected for real.

Returns items under the data tool contract (#17): the profile, then own Premium projects, then survey facts."""
import json

from fx_data.records import ProducerRecords
from tests.tool_harness import call_tool

from fex.tools.producer_record import get_producer_record

RECORDS = ProducerRecords.load()._records
WITH_SURVEY = next(pid for pid, r in RECORDS.items() if r["survey"]["facts"])
NO_SURVEY = next(pid for pid, r in RECORDS.items() if r["survey"]["responses"] == 0)


def test_model_cannot_set_any_parameter():
    assert get_producer_record.tool_spec["inputSchema"]["json"]["properties"] == {}


def test_returns_only_the_session_producers_own_record():
    status, items = call_tool(get_producer_record, {}, {"producer_id": WITH_SURVEY})
    own = RECORDS[WITH_SURVEY]
    assert status == "success" and items
    profile, *rest = items
    assert profile["source"] == own["profile"]["source"]
    assert {k: v for k, v in own["profile"].items() if k != "source"} == profile["data"]
    projects = [i["data"] for i in rest if "project_ref" in i["data"]]
    assert projects == [{k: v for k, v in p.items() if k != "source"} for p in own["premium_projects"]]


def test_items_follow_the_data_tool_contract():
    _, items = call_tool(get_producer_record, {}, {"producer_id": WITH_SURVEY})
    for item in items:
        assert set(item) == {"source", "kind", "text", "period", "strength", "data"}
        assert item["kind"] == "producer_record" and item["source"] and item["text"]
        assert item["strength"] in {"exact", "nearest", "limited"}


def test_a_producer_id_supplied_by_the_model_is_ignored():
    _, honest = call_tool(get_producer_record, {}, {"producer_id": WITH_SURVEY})
    _, spoofed = call_tool(get_producer_record, {"producer_id": NO_SURVEY}, {"producer_id": WITH_SURVEY})
    assert spoofed == honest


def test_works_for_producers_with_no_survey_data():
    status, items = call_tool(get_producer_record, {}, {"producer_id": NO_SURVEY})
    assert status == "success" and items  # the profile is still there
    survey_sources = {f["source"] for r in RECORDS.values() for f in r["survey"]["facts"]}
    assert not [i for i in items if i["source"] in survey_sources]


def test_survey_facts_are_returned_as_items():
    _, items = call_tool(get_producer_record, {}, {"producer_id": WITH_SURVEY})
    texts = {i["text"] for i in items}
    assert {f["text"] for f in RECORDS[WITH_SURVEY]["survey"]["facts"]} <= texts


def test_no_sensitive_survey_topics_are_returned():
    for pid in RECORDS:
        _, items = call_tool(get_producer_record, {}, {"producer_id": pid})
        text = json.dumps([i for i in items if "responses" in i["data"]]).lower()
        # "income" is not listed: "I diversified my income sources" is an allowed fishing-adaptation answer.
        for word in ("harass", "discrim", "borrow", "loan", "medical", "child", "leadership", "committee"):
            assert word not in text, (pid, word)


def test_unknown_producer_gets_an_empty_list():
    assert call_tool(get_producer_record, {}, {"producer_id": "NOT-A-PRODUCER"}) == ("success", [])


def test_no_producer_in_session_is_refused():
    status, text = call_tool(get_producer_record, {}, {})
    assert status == "error" and "No producer in session" in text
