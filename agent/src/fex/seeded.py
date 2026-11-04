"""Seeded conversation records for the dashboard (issue #37): validate, then upload to S3.

Spec: docs/specs/37-seeded-records.md. The generator is `fx_data.seeded_records` in the data package; it
cannot validate against the record models because they live here and the data package must not import the
agent package. So this module validates every record with `parse_record` before anything is written:
an invalid record is an error and nothing is uploaded.

Seeded records go only to S3, one plain-JSON object per record under `records-seeded/` in the records
bucket. They are never written to DynamoDB, so they never reach the reviewer queue, evals or the
Journey 3 join. Re-running replaces the set: objects under the prefix that are not in the new set are
deleted. Objects outside the prefix are never touched.

The deploy step: `uv run python scripts/load_seeded_records.py --bucket <records bucket>`.

Follow-up, with the Athena sync stack (#28, infra/lib/athena-sync-stack.ts): the separate Glue table over
`records-seeded/` (same columns as the live records table) and running this script as a deploy step
belong in that stack and are not part of this module.
"""
import json
from dataclasses import dataclass

from fex.models import parse_record
from fx_data.seeded_records import generate_seeded_records

SEEDED_PREFIX = "records-seeded/"


@dataclass(frozen=True)
class UploadResult:
    written: int
    deleted: int


def validated_seeded_records(records: list[dict] | None = None) -> list[dict]:
    """Every record validated with the record models and dumped as plain JSON with every model field
    (so the objects carry the same columns as live records). Raises on the first invalid record."""
    records = generate_seeded_records() if records is None else records
    return [parse_record(r).model_dump(mode="json") for r in records]


def _key(record: dict) -> str:
    return f"{SEEDED_PREFIX}{record['record_id']}.json"


def upload_seeded_records(s3, bucket: str, records: list[dict] | None = None) -> UploadResult:
    """Replace the seeded set in `bucket` with `records` (default: the generated set)."""
    validated = validated_seeded_records(records)  # all of them, before any write
    keys = [_key(r) for r in validated]
    if len(set(keys)) != len(keys):
        raise ValueError("seeded records must have unique record IDs")
    for key, record in zip(keys, validated):
        s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(record, ensure_ascii=False).encode("utf-8"),
                      ContentType="application/json")
    wanted = set(keys)
    stale = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=SEEDED_PREFIX)
             for o in page.get("Contents", []) if o["Key"] not in wanted]
    refused = []
    for i in range(0, len(stale), 1000):  # delete_objects takes at most 1000 keys
        response = s3.delete_objects(Bucket=bucket,
                                     Delete={"Objects": [{"Key": k} for k in stale[i:i + 1000]], "Quiet": True})
        # S3 reports per-object failures inside a successful response, not as an exception
        refused += [f"{e.get('Key')} ({e.get('Code')})" for e in response.get("Errors", [])]
    if refused:
        raise RuntimeError(f"seeded set not replaced: S3 refused to delete {len(refused)} stale object(s): "
                           + ", ".join(refused[:10]))
    return UploadResult(written=len(keys), deleted=len(stale))
