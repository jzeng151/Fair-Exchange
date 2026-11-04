"""Rebuild the S3 objects from DynamoDB (spec 28). The repair path for anything the stream missed.

Usage: RECORDS_TABLE=<table> SYNC_BUCKET=<bucket> uv run python -m fex_sync.resync
"""
import logging
from collections import Counter

from .store import bucket_name, default_s3, default_table, list_object_record_ids, scan_record_ids
from .sync import sync_record


def resync(s3, bucket: str, table) -> Counter:
    """Publish every record and delete objects whose record no longer exists.

    The scan only supplies IDs. Each ID gets a fresh consistent read inside `sync_record`,
    so a stale scanned copy is never published, and the version check in `publish_record`
    stops this from overwriting a newer object written by the stream consumer meanwhile.
    """
    counts: Counter = Counter()
    scanned = set(scan_record_ids(table))
    for record_id in scanned:
        counts[sync_record(s3, bucket, table, record_id)] += 1
    # Objects with no row in the scan: sync_record re-reads and deletes them if the record is truly gone
    for record_id in set(list_object_record_ids(s3, bucket)) - scanned:
        counts[sync_record(s3, bucket, table, record_id)] += 1
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    counts = resync(default_s3(), bucket_name(), default_table())
    print(dict(counts))


if __name__ == "__main__":
    main()
