"""Issue #26: write-back. Records are built from the conversation state and saved by code at fixed points.

Spec: docs/specs/26-write-back.md. Seam 1 (agent entrypoint) with the record store on moto DynamoDB,
so conditional writes behave as in AWS.
"""
import boto3
import pytest
from moto import mock_aws
from pydantic import ValidationError
from tests.conversation_harness import RETRIEVE, Run, answer, claim, of, playback, summary

from fex.models import ConsentChoice, parse_record
from fex.records import DynamoRecordStore, RecordConflict, save_record

TABLE = "fair-exchange-records-test"
NARRATIVE = {"language", "entity_type", "summary_original", "summary_english", "tags", "evidence",
             "earlier_answers", "insights", "peer_examples", "feedback", "reviewer_tags",
             "reviewer_summary_original", "reviewer_summary_english"}


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        t = ddb.create_table(TableName=TABLE, KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                             AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                             BillingMode="PAY_PER_REQUEST")
        yield t


@pytest.fixture
def run(table):
    return Run(records=DynamoRecordStore(table))


def items(table) -> list[dict]:
    return table.scan()["Items"]


def stored(table, run) -> dict:
    found = [i for i in items(table) if i["record_id"] == run.conversation_id]
    assert len(found) == 1
    return found[0]


# ---------------------------------------------------------------- save points

def test_nothing_is_saved_before_the_first_save_point(run, table):
    run.to_consent()
    assert items(table) == []


def test_one_record_per_conversation_across_repeated_saves(run, table):
    run.to_consent()
    run.action("set_consent", scope="internal")
    run.action("set_feedback", value="somewhat")
    run.action("end")
    assert len(items(table)) == 1
    record = stored(table, run)
    assert record["record_id"] == run.conversation_id and int(record["version"]) == 3
    assert record["source"] == "agent conversation"


def test_each_save_emits_record_saved(run):
    run.to_consent()
    events = run.action("set_consent", scope="internal_and_outward")
    saved = of(events, "record_saved")
    assert len(saved) == 1
    assert (saved[0].status, saved[0].consent_scope, saved[0].version) == ("completed", "internal_and_outward", 1)
    assert of(run.action("set_feedback", value="yes"), "record_saved")[0].version == 2


def test_repeated_identical_actions_write_nothing(run, table):
    run.to_feedback()
    before = stored(table, run)
    events = run.action("set_consent", scope="internal")
    assert of(events, "record_saved") == []
    assert stored(table, run) == before


def test_a_save_that_would_change_nothing_writes_nothing(run, table):
    run.to_feedback()
    store = DynamoRecordStore(table)
    assert save_record(run.state(), store, run.engine.clock()) is None
    assert int(stored(table, run)["version"]) == 1


def test_end_without_any_consent_choice_saves_no_record(run, table):
    run.to_consent()
    run.action("end")
    assert items(table) == []  # spec: "Not decided"; nothing is built or assumed


def test_closed_at_is_set_on_end_and_on_auto_close(table):
    for close in (lambda r: r.action("end"), lambda r: r.send("auto_close", reason="inactivity")):
        r = Run(records=DynamoRecordStore(table))
        r.conversation_id = f"conv-close-{len(items(table))}"
        r.to_feedback()
        assert stored(table, r).get("closed_at") is None
        close(r)
        assert stored(table, r)["closed_at"]


# ---------------------------------------------------------------- building the record

def test_completed_record_is_built_from_the_state_and_validates(run, table):
    run.to_feedback()
    run.action("set_feedback", value="yes")
    record = parse_record(stored(table, run))
    s = run.state()
    assert record.status == "completed" and record.producer_id == run.producer_id
    assert (record.summary_original, record.summary_english, record.tags) == \
        (s.playback.summary_original, s.playback.summary_english, s.playback.tags)
    assert record.language == "es" and record.feedback == "yes" and record.evidence == "full"
    assert [c.text for c in record.insights] == ["Rainfall fell."]
    assert record.consent.scope == "internal" and [c.scope for c in record.consent_history] == ["internal"]


def test_declined_record_has_no_narrative_fields(run, table):
    run.to_consent()
    run.action("set_consent", scope="declined")
    record = stored(table, run)
    assert record["status"] == "declined" and not NARRATIVE & set(record)
    assert [c["scope"] for c in record["consent_history"]] == ["declined"]


def test_completed_record_carries_the_decision_log_with_ids_only(run, table):
    run.to_playback()
    run.small.add(summary())
    invented = claim("Rainfall fell.", "Notes from a visit [Juan Pérez, 555-0100]", clause="APS 2.1.1")
    run.large.add(*RETRIEVE, *[answer([invented], [])] * 3)
    run.action("confirm_playback")
    run.action("set_consent", scope="internal")
    record = parse_record(stored(table, run))
    assert record.decision_log == run.state().decision_log
    assert ("verifier", "unknown_source", ["APS 2.1.1"]) in [(e.kind, e.code, e.refs) for e in record.decision_log]
    assert not any("Juan" in ref or "555" in ref for e in record.decision_log for ref in e.refs)


def test_declined_record_has_no_decision_log(run, table):
    run.to_consent()
    run.action("set_consent", scope="declined")
    assert "decision_log" not in stored(table, run)


def test_completed_declined_completed_switching_keeps_earlier_answers(run, table):
    run.to_consent()
    run.action("reopen_playback")
    run.small.add(summary())
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    run.action("set_consent", scope="internal")
    assert stored(table, run)["status"] == "completed"
    run.action("set_consent", scope="declined")
    assert stored(table, run)["status"] == "declined"
    run.action("set_consent", scope="internal")
    record = parse_record(stored(table, run))
    assert record.status == "completed"
    assert [a.reason for a in record.earlier_answers] == ["reopened"]
    assert [c.scope for c in record.consent_history] == ["internal", "declined", "internal"]
    assert record.version == 3


def test_limited_evidence_is_marked_on_the_record(run, table):
    run.to_playback()
    run.small.add(summary())
    run.large.add(*RETRIEVE, answer([], [claim("Peer.", run.peers[0]["source"])]))
    run.action("confirm_playback")
    run.action("set_consent", scope="internal")
    assert stored(table, run)["evidence"] == "limited"


def test_summaries_and_tags_are_unchanged_by_later_saves_until_a_reconfirm(run, table):
    run.to_feedback()
    first = stored(table, run)
    run.action("set_feedback", value="no")
    assert (stored(table, run)["tags"], stored(table, run)["summary_original"]) == \
        (first["tags"], first["summary_original"])
    run.action("reopen_playback")
    run.small.add(("out", "RecordSummary", {"summary_original": "Fue granizo.", "summary_english": "It was hail.",
                                            "tags": ["climate and weather"]}))
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    run.action("set_consent", scope="internal")
    after = stored(table, run)
    assert after["tags"] == ["climate and weather"] and after["summary_original"] == "Fue granizo."


def test_claims_shown_before_a_failed_answer_are_kept_as_interrupted(run, table):
    run.to_playback()
    run.small.add(summary())
    run.large.add(*RETRIEVE, answer([claim("Invented.", "Made-up")], [claim("Peer.", run.peers[0]["source"])]),
                  ("raise", RuntimeError("throttled")))
    run.action("confirm_playback")
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("retry_answer")
    run.action("set_consent", scope="internal")
    record = parse_record(stored(table, run))
    assert [(a.reason, [c.text for c in a.peer_examples]) for a in record.earlier_answers] == [("interrupted", ["Peer."])]


def test_entity_type_correction_reaches_the_record(run, table):
    run.small.add(("out", "IntakeTurn", {"reply": "Hola", "ready_for_playback": False, "language": "es"}),
                  ("out", "IntakeTurn", {"reply": "", "ready_for_playback": True, "language": "es"}),
                  playback(entity_type="estate"))
    run.send("start")
    run.send("message", text="Somos una finca.")
    run.small.add(summary())
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    run.action("set_consent", scope="internal")
    assert stored(table, run)["entity_type"] == "estate"


# ---------------------------------------------------------------- write rules

def test_a_create_never_overwrites_an_existing_record(run, table):
    run.to_feedback()
    store = DynamoRecordStore(table)
    record = parse_record(stored(table, run))
    with pytest.raises(RecordConflict):
        store.create(record)


def test_a_stale_version_is_rejected(run, table):
    run.to_feedback()
    store = DynamoRecordStore(table)
    record = parse_record(stored(table, run)).model_copy(update={"version": 2})
    with pytest.raises(RecordConflict):
        store.update(record, expected_version=5)
    assert int(stored(table, run)["version"]) == 1


def test_a_different_producer_cannot_update_the_record(run, table):
    run.to_feedback()
    store = DynamoRecordStore(table)
    record = parse_record(stored(table, run))
    hijack = record.model_copy(update={"producer_id": "SOMEONE-ELSE", "version": 2})
    with pytest.raises(RecordConflict):
        store.update(hijack, expected_version=1)
    assert stored(table, run)["producer_id"] == run.producer_id


def test_a_conflict_is_surfaced_as_an_error_event_and_not_retried(run, table):
    run.to_feedback()
    table.update_item(Key={"record_id": run.conversation_id}, UpdateExpression="SET version = :v",
                      ExpressionAttributeValues={":v": 9})  # someone else wrote: a bug, per the spec
    events = run.action("set_feedback", value="yes")
    assert of(events, "record_saved") == []
    assert of(events, "error")[0].code == "agent_failed"
    assert int(stored(table, run)["version"]) == 9


def test_an_invalid_record_is_an_error_not_a_partial_write(run, table):
    run.to_consent()
    s = run.state()
    s.playback.summary_english = None  # a Spanish conversation without its English summary
    s.consent, s.step = "internal", "feedback"
    s.consent_history.append(ConsentChoice(scope="internal", recorded_at=run.engine.clock()))
    with pytest.raises(ValidationError):
        save_record(s, DynamoRecordStore(table), run.engine.clock())
    assert items(table) == []
