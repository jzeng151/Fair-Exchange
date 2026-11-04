from fex_sync.publish import publish_record, to_json

from conftest import BUCKET, make_record, stored


class RacingS3:
    """Wraps an S3 client; runs `before_put` once, just before the first put_object (a competing writer)."""

    def __init__(self, s3, before_put):
        self._s3, self._before_put = s3, before_put

    def put_object(self, **kwargs):
        before_put, self._before_put = self._before_put, None
        if before_put:
            before_put()
        return self._s3.put_object(**kwargs)

    def __getattr__(self, name):
        return getattr(self._s3, name)


def publish(s3, record):
    return publish_record(s3, BUCKET, record["record_id"], lambda: record)


def test_first_publish_writes_the_object(aws):
    s3, _ = aws
    assert publish(s3, make_record(version=1)) == "written"
    assert stored(s3, "r1")[1]["record-version"] == "1"


def test_newer_version_replaces_older(aws):
    s3, _ = aws
    publish(s3, make_record(version=1))
    assert publish(s3, make_record(version=2, review_status="reviewed")) == "written"
    body, metadata = stored(s3, "r1")
    assert body["review_status"] == "reviewed" and metadata["record-version"] == "2"


def test_older_or_equal_version_never_overwrites(aws):
    s3, _ = aws
    publish(s3, make_record(version=5, review_status="reviewed"))
    assert publish(s3, make_record(version=4)) == "skipped"
    assert publish(s3, make_record(version=5)) == "skipped"
    body, metadata = stored(s3, "r1")
    assert body["review_status"] == "reviewed" and metadata["record-version"] == "5"


def test_resync_holding_n_loses_to_stream_consumer_publishing_n_plus_1(aws):
    """Resync read version 1; before it writes, the stream consumer publishes version 2 (consent declined)."""
    s3, table = aws
    declined = {"record_id": "r1", "producer_id": "p1", "version": 2, "status": "declined",
                "consent": {"scope": "declined", "recorded_at": "2026-11-04T11:00:00Z"}}
    table.put_item(Item=declined)  # DynamoDB already holds the newest state
    old = make_record(version=1)
    reads = iter([old, declined])  # the first (stale) read is what resync "held"

    racing = RacingS3(s3, lambda: publish(s3, declined))
    result = publish_record(racing, BUCKET, "r1", lambda: next(reads))
    assert result == "skipped"  # the failed condition caused a fresh read, which found version 2 already there
    body, metadata = stored(s3, "r1")
    assert body["status"] == "declined" and metadata["record-version"] == "2"
    assert "summary_original" not in body


def test_failed_condition_is_retried_with_a_fresh_read(aws):
    s3, _ = aws
    publish(s3, make_record(version=1))
    # A competing writer publishes version 2 between our read and write; our record is version 3
    racing = RacingS3(s3, lambda: publish(s3, make_record(version=2)))
    assert publish_record(racing, BUCKET, "r1", lambda: make_record(version=3)) == "written"
    assert stored(s3, "r1")[1]["record-version"] == "3"


def test_first_write_race_uses_if_none_match(aws):
    s3, _ = aws
    racing = RacingS3(s3, lambda: publish(s3, make_record(version=2)))
    assert publish_record(racing, BUCKET, "r1", lambda: make_record(version=1)) == "skipped"
    assert stored(s3, "r1")[1]["record-version"] == "2"


def test_missing_record_is_reported_not_written(aws):
    s3, _ = aws
    assert publish_record(s3, BUCKET, "gone", lambda: None) == "missing"
    assert stored(s3, "gone") is None


def test_json_is_plain_and_decimals_become_numbers():
    from decimal import Decimal
    assert to_json({"a": Decimal("2"), "b": Decimal("1.5")}) == b'{"a":2,"b":1.5}'
