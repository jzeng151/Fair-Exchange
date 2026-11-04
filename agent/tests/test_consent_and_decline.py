"""Issue #19: consent and decline. Spec: docs/specs/19-consent-and-decline.md.

Most of #19 was built with #13 (consent steps and actions) and #26 (records). This file checks each case in
the #19 spec's "Testing Decisions" at the record level, through the agent entrypoint (seam 1, moto DynamoDB).
"""
import boto3
import pytest
from moto import mock_aws
from tests.conversation_harness import RETRIEVE, Run, of, short_reply, summary

from fex.models import parse_record
from fex.records import DynamoRecordStore

NARRATIVE = {"language", "entity_type", "summary_original", "summary_english", "tags", "evidence",
             "earlier_answers", "insights", "peer_examples", "feedback"}


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        yield ddb.create_table(TableName="records", KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                               AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                               BillingMode="PAY_PER_REQUEST")


@pytest.fixture
def run(table):
    r = Run(records=DynamoRecordStore(table))
    r.table = table
    return r


def record(run) -> dict:
    items = run.table.scan()["Items"]
    assert len(items) == 1
    return items[0]


@pytest.mark.parametrize("scope, status", [
    ("internal", "completed"), ("internal_and_outward", "completed"), ("declined", "declined"),
])
def test_each_consent_value_produces_the_right_record_type(run, scope, status):
    run.to_consent()
    run.action("set_consent", scope=scope)
    saved = parse_record(record(run))
    assert saved.status == status and saved.consent.scope == scope


def test_granted_declined_granted_ends_completed_with_three_history_entries_in_order(run):
    run.to_consent()
    for scope in ("internal", "declined", "internal_and_outward"):
        run.action("set_consent", scope=scope)
    saved = parse_record(record(run))
    assert saved.status == "completed"
    assert [c.scope for c in saved.consent_history] == ["internal", "declined", "internal_and_outward"]
    times = [c.recorded_at for c in saved.consent_history]
    assert times == sorted(times)
    assert saved.consent.recorded_at == times[-1]  # consent.recorded_at is the latest choice


def test_the_same_choice_twice_adds_one_entry(run):
    run.to_consent()
    run.action("set_consent", scope="internal")
    events = run.action("set_consent", scope="internal")
    assert of(events, "record_saved") == []
    assert [c["scope"] for c in record(run)["consent_history"]] == ["internal"]


def test_end_after_a_granted_choice_keeps_it_in_the_record(run):
    run.to_consent()
    run.action("set_consent", scope="internal_and_outward")
    run.action("end")
    saved = parse_record(record(run))
    assert saved.status == "completed" and saved.consent.scope == "internal_and_outward" and saved.closed_at


def test_a_declined_record_carries_no_narrative_field(run):
    run.to_feedback()
    run.action("set_feedback", value="yes")
    run.action("set_consent", scope="declined")  # after feedback: feedback is cleared too
    saved = record(run)
    assert saved["status"] == "declined" and not NARRATIVE & set(saved)


def test_a_reopen_clears_consent_without_adding_a_history_entry(run):
    run.to_consent()
    run.action("set_consent", scope="internal")
    run.action("reopen_playback")
    state = run.state()
    assert state.consent is None and state.step == "playback"
    assert [c.scope for c in state.consent_history] == ["internal"]  # only the producer's own choices
    run.small.add(summary())
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    assert run.state().step == "consent" and "set_consent" in run.send("resume").allowed  # asked again


def test_typed_text_in_consent_leaves_consent_unchanged(run):
    run.to_consent()
    run.action("set_consent", scope="declined")
    run.small.add(short_reply("Puede cambiarlo cuando quiera."))
    run.send("message", text="Sí, guárdelo y compártalo con todos.")
    assert run.state().consent == "declined"
    assert record(run)["status"] == "declined"


def test_declining_clears_feedback_so_switching_back_does_not_restore_it(run):
    run.to_feedback()
    run.action("set_feedback", value="no")
    run.action("set_consent", scope="declined")
    run.action("set_consent", scope="internal")
    saved = parse_record(record(run))
    assert saved.status == "completed" and saved.feedback is None  # asked again, not carried over
