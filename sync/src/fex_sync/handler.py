"""Lambda: DynamoDB Streams consumer for the records table (spec 28).

Stream records are keys-only and used purely as a signal that a record changed.
Failures are reported per item (partial batch response) so one bad record does not block the rest.
"""
import logging
from typing import Any

from .store import bucket_name, default_s3, default_table
from .sync import sync_record

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_clients: dict[str, Any] = {}


def _table():
    return _clients.setdefault("table", default_table())


def _s3():
    return _clients.setdefault("s3", default_s3())


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, list[dict[str, str]]]:
    # Several events can name the same record; sync it once and fail all of its events together
    sequence_numbers: dict[str, list[str]] = {}
    for stream_record in event.get("Records", []):
        record_id = stream_record["dynamodb"]["Keys"]["record_id"]["S"]
        sequence_numbers.setdefault(record_id, []).append(stream_record["dynamodb"]["SequenceNumber"])

    failures: list[dict[str, str]] = []
    for record_id, sequences in sequence_numbers.items():
        try:
            outcome = sync_record(_s3(), bucket_name(), _table(), record_id)
            logger.info("synced record %s: %s", record_id, outcome)
        except Exception:
            logger.exception("failed to sync record %s", record_id)
            failures.extend({"itemIdentifier": sequence} for sequence in sequences)
    return {"batchItemFailures": failures}
