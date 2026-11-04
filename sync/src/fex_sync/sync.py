"""Sync one record, shared by the stream consumer and the resync command."""
from .publish import PublishResult, delete_record_object, publish_record
from .store import reader


def sync_record(s3, bucket: str, table, record_id: str) -> PublishResult | str:
    """Make the S3 object match the record's current state in DynamoDB.

    Re-reads the record (never trusts an event or a scanned copy). If the record is gone, deletes the object.
    """
    result = publish_record(s3, bucket, record_id, reader(table, record_id))
    if result == "missing":
        delete_record_object(s3, bucket, record_id)
        return "deleted"
    return result
