from fex_sync import handler as handler_module
from fex_sync.handler import handler

from conftest import make_record, stored, stream_event


def run(event):
    handler_module._clients.clear()
    return handler(event)


def test_changed_record_is_written_as_plain_json(aws):
    s3, table = aws
    table.put_item(Item=make_record("r1", version=2))
    assert run(stream_event("r1")) == {"batchItemFailures": []}
    body, metadata = stored(s3, "r1")
    assert body["record_id"] == "r1"
    assert body["version"] == 2  # an int, not a DynamoDB-typed {"N": "2"} or a Decimal string
    assert body["tags"] == ["climate and weather"]
    assert metadata["record-version"] == "2"


def test_old_event_writes_current_state_not_the_old_one(aws):
    s3, table = aws
    table.put_item(Item=make_record("r1", version=1))
    event_for_version_1 = stream_event("r1")
    # The producer then declines: the record changes before the old event is processed
    table.put_item(Item={"record_id": "r1", "producer_id": "p1", "version": 2, "status": "declined",
                         "consent": {"scope": "declined", "recorded_at": "2026-11-04T11:00:00Z"}})
    run(event_for_version_1)
    body, _ = stored(s3, "r1")
    assert body["status"] == "declined"
    assert "summary_original" not in body  # declined narrative never comes back


def test_replayed_old_event_does_not_regress_the_object(aws):
    s3, table = aws
    table.put_item(Item=make_record("r1", version=3))
    run(stream_event("r1"))
    run(stream_event("r1"))
    assert stored(s3, "r1")[1]["record-version"] == "3"


def test_event_for_deleted_record_deletes_the_object(aws):
    s3, table = aws
    table.put_item(Item=make_record("r1"))
    run(stream_event("r1"))
    assert stored(s3, "r1") is not None
    table.delete_item(Key={"record_id": "r1"})
    run(stream_event("r1"))
    assert stored(s3, "r1") is None


def test_one_failing_record_is_reported_without_blocking_the_rest(aws):
    s3, table = aws
    table.put_item(Item=make_record("good1"))
    table.put_item(Item=make_record("bad", version=None))  # no integer version: cannot be published
    table.put_item(Item=make_record("good2"))
    result = run(stream_event("good1", "bad", "good2"))
    assert result == {"batchItemFailures": [{"itemIdentifier": "001"}]}
    assert stored(s3, "good1") is not None
    assert stored(s3, "good2") is not None
    assert stored(s3, "bad") is None


def test_duplicate_events_for_one_record_fail_together(aws):
    _, table = aws
    table.put_item(Item=make_record("bad", version=None))
    result = run(stream_event("bad", "bad"))
    assert result == {"batchItemFailures": [{"itemIdentifier": "000"}, {"itemIdentifier": "001"}]}
