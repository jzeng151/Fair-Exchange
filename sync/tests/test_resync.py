from fex_sync.publish import object_key
from fex_sync.resync import resync

from conftest import BUCKET, make_record, stored


def test_missing_object_is_written(aws):
    s3, table = aws
    table.put_item(Item=make_record("r1"))
    assert resync(s3, BUCKET, table)["written"] == 1
    assert stored(s3, "r1") is not None


def test_orphaned_object_is_deleted(aws):
    s3, table = aws
    s3.put_object(Bucket=BUCKET, Key=object_key("orphan"), Body=b"{}", Metadata={"record-version": "1"})
    assert resync(s3, BUCKET, table)["deleted"] == 1
    assert stored(s3, "orphan") is None


def test_up_to_date_objects_are_left_alone(aws):
    s3, table = aws
    table.put_item(Item=make_record("r1"))
    resync(s3, BUCKET, table)
    assert resync(s3, BUCKET, table)["skipped"] == 1


def test_stale_object_is_replaced_with_current_state(aws):
    s3, table = aws
    table.put_item(Item=make_record("r1", version=1))
    resync(s3, BUCKET, table)
    table.put_item(Item=make_record("r1", version=2, review_status="reviewed"))
    resync(s3, BUCKET, table)
    assert stored(s3, "r1")[0]["review_status"] == "reviewed"


def test_scan_pages_are_all_processed(aws):
    s3, table = aws
    for i in range(30):
        table.put_item(Item=make_record(f"r{i:02d}"))
    assert resync(s3, BUCKET, table)["written"] == 30
