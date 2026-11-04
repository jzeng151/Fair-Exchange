"""Issue #23: feedback capture. Spec: docs/specs/23-feedback-capture.md.

Feedback was built with #13 (the `feedback` step and `set_feedback`) and #26 (records). This file checks each
case in the #23 spec's "Testing Decisions" through the agent entrypoint (seam 1), at the record level.
"""
import boto3
import pytest
from moto import mock_aws
from tests.conversation_harness import Run, allowed, of

from fex.models import parse_record
from fex.records import DynamoRecordStore


@pytest.fixture
def run():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        table = ddb.create_table(TableName="records", KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                                 AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                                 BillingMode="PAY_PER_REQUEST")
        r = Run(records=DynamoRecordStore(table))
        r.table = table
        yield r


def record(run) -> dict:
    items = run.table.scan()["Items"]
    assert len(items) == 1
    return items[0]


def test_feedback_is_asked_after_granted_consent(run):
    run.to_consent()
    events = run.action("set_consent", scope="internal")
    assert of(events, "step")[-1].step == "feedback" and "set_feedback" in allowed(events)


@pytest.mark.parametrize("value", ["yes", "somewhat", "no"])
def test_feedback_is_stored_on_the_completed_record(run, value):
    run.to_feedback()
    run.action("set_feedback", value=value)
    saved = parse_record(record(run))
    assert saved.status == "completed" and saved.feedback == value


def test_only_the_three_choices_are_accepted(run):
    run.to_feedback()
    with pytest.raises(ValueError):
        run.action("set_feedback", value="maybe")


def test_a_changed_answer_replaces_the_earlier_one(run):
    run.to_feedback()
    run.action("set_feedback", value="no")
    events = run.action("set_feedback", value="yes")
    assert of(events, "record_saved")  # each answer saves the record
    assert record(run)["feedback"] == "yes"


def test_end_without_an_answer_leaves_feedback_empty(run):
    run.to_feedback()
    run.action("end")
    saved = parse_record(record(run))
    assert saved.closed_at and saved.feedback is None


def test_feedback_is_never_asked_after_a_decline(run):
    run.to_consent()
    events = run.action("set_consent", scope="declined")
    assert run.state().step == "consent" and "set_feedback" not in allowed(events)
    rejected = run.action("set_feedback", value="yes")
    assert of(rejected, "error")[0].code == "invalid_action"
    assert "feedback" not in record(run)


def test_changing_consent_to_declined_clears_feedback(run):
    run.to_feedback()
    run.action("set_feedback", value="somewhat")
    run.action("set_consent", scope="declined")
    assert run.state().feedback is None
    assert record(run)["status"] == "declined" and "feedback" not in record(run)
