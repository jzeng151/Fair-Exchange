"""The one place that writes record objects to S3 (spec 28).

Both the stream consumer and the resync command call `publish_record`, so neither can
overwrite a newer version with an older one.
"""
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Literal

from botocore.exceptions import ClientError

RECORDS_PREFIX = "records/"
VERSION_METADATA_KEY = "record-version"
MAX_ATTEMPTS = 5

PublishResult = Literal["written", "skipped", "missing"]


def object_key(record_id: str) -> str:
    return f"{RECORDS_PREFIX}{record_id}.json"


def should_publish(record: dict[str, Any]) -> bool:
    """The single place to filter which records reach Athena.

    Whether records of still-open conversations appear is not decided (spec 28), so every record is copied.
    """
    return True


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def to_json(record: dict[str, Any]) -> bytes:
    """Plain JSON (unmarshalled, not DynamoDB-typed), one object per line-free document."""
    return json.dumps(record, default=_json_default, separators=(",", ":"), sort_keys=True).encode("utf-8")


def record_version(record: dict[str, Any]) -> int:
    version = record.get("version")
    if isinstance(version, bool) or not isinstance(version, (int, Decimal)):
        raise ValueError(f"record {record.get('record_id')!r} has no integer version")
    return int(version)


def _current_object(s3, bucket: str, key: str) -> tuple[int, str] | None:
    """The stored object's (version, ETag), or None if there is no object."""
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    version = head.get("Metadata", {}).get(VERSION_METADATA_KEY)
    # An object without a version is treated as older than any record
    return (int(version) if version is not None else -1), head["ETag"]


def _is_condition_failure(error: ClientError) -> bool:
    return error.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict")


def publish_record(
    s3, bucket: str, record_id: str, read_current: Callable[[], dict[str, Any] | None],
) -> PublishResult:
    """Write the record's current state unless the object already holds the same or a newer version.

    `read_current` does a fresh, strongly consistent read of the record from DynamoDB. It is called
    again on every retry, so a lost race never publishes a stale copy.
    Returns "missing" when the record no longer exists (the caller decides what to do about the object).
    """
    key = object_key(record_id)
    for _ in range(MAX_ATTEMPTS):
        record = read_current()
        if record is None:
            return "missing"
        if not should_publish(record):
            return "skipped"
        version = record_version(record)
        existing = _current_object(s3, bucket, key)
        if existing is not None and existing[0] >= version:
            return "skipped"
        condition = {"IfMatch": existing[1]} if existing else {"IfNoneMatch": "*"}
        try:
            s3.put_object(
                Bucket=bucket, Key=key, Body=to_json(record), ContentType="application/json",
                Metadata={VERSION_METADATA_KEY: str(version)}, **condition,
            )
            return "written"
        except ClientError as error:
            if not _is_condition_failure(error):
                raise
    raise RuntimeError(f"could not publish record {record_id!r} after {MAX_ATTEMPTS} attempts")


def delete_record_object(s3, bucket: str, record_id: str) -> None:
    s3.delete_object(Bucket=bucket, Key=object_key(record_id))
