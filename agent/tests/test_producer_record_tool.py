"""Producer-record tool (#14), called through Strands so the session context is injected for real."""
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
    status, record = call_tool(get_producer_record, {}, {"producer_id": WITH_SURVEY})
    assert status == "success" and record["found"]
    assert record["profile"] == RECORDS[WITH_SURVEY]["profile"]
    assert record["premium_projects"] == RECORDS[WITH_SURVEY]["premium_projects"]


def test_a_producer_id_supplied_by_the_model_is_ignored():
    _, honest = call_tool(get_producer_record, {}, {"producer_id": WITH_SURVEY})
    _, spoofed = call_tool(get_producer_record, {"producer_id": NO_SURVEY}, {"producer_id": WITH_SURVEY})
    assert spoofed == honest


def test_works_for_producers_with_no_survey_data():
    status, record = call_tool(get_producer_record, {}, {"producer_id": NO_SURVEY})
    assert status == "success" and record["found"]
    assert record["survey"]["facts"] == [] and record["survey"]["note"]


def test_everything_returned_can_be_cited():
    _, record = call_tool(get_producer_record, {}, {"producer_id": WITH_SURVEY})
    items = [record["profile"]] + record["premium_projects"] + record["survey"]["facts"]
    assert all(item["source"] for item in items)


def test_no_sensitive_survey_topics_are_returned():
    for pid in RECORDS:
        _, record = call_tool(get_producer_record, {}, {"producer_id": pid})
        text = json.dumps(record["survey"]).lower()
        # "income" is not listed: "I diversified my income sources" is an allowed fishing-adaptation answer.
        for word in ("harass", "discrim", "borrow", "loan", "medical", "child", "leadership", "committee"):
            assert word not in text, (pid, word)


def test_unknown_producer_gets_no_record():
    status, record = call_tool(get_producer_record, {}, {"producer_id": "NOT-A-PRODUCER"})
    assert status == "success" and record == {"found": False, "note": "No record on file for this producer."}


def test_no_producer_in_session_is_refused():
    status, text = call_tool(get_producer_record, {}, {})
    assert status == "error" and "No producer in session" in text
