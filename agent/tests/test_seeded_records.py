"""Seeded conversation records for the dashboard (#37): validation with the record models and upload.

The generator is in the data package (fx_data.seeded_records, tested in data/tests). Validation and upload
live here because the record models do. S3 is moto, so no AWS calls are made.
"""
import json

import boto3
import pytest
from moto import mock_aws
from pydantic import ValidationError

from fex.models import CompletedRecord, DeclinedRecord, parse_record
from fex.seeded import SEEDED_PREFIX, upload_seeded_records, validated_seeded_records
from fx_data.seeded_records import generate_seeded_records

BUCKET = "fx-records-test"


def test_every_seeded_record_passes_parse_record():
    records = generate_seeded_records()
    parsed = [parse_record(r) for r in records]
    assert {type(p) for p in parsed} == {CompletedRecord, DeclinedRecord}


def test_validated_records_are_plain_json_with_every_model_field():
    out = validated_seeded_records()
    assert len(out) == len(generate_seeded_records())
    assert json.loads(json.dumps(out)) == out
    completed = next(r for r in out if r["status"] == "completed")
    assert set(completed) == set(CompletedRecord.model_fields)
    declined = next(r for r in out if r["status"] == "declined")
    assert set(declined) == set(DeclinedRecord.model_fields)


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-west-2")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        yield client


def _keys(s3) -> set[str]:
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET)
    return {o["Key"] for p in pages for o in p.get("Contents", [])}


def _small_set():
    return generate_seeded_records()[:5]


def test_upload_writes_one_json_object_per_record_only_under_the_seeded_prefix(s3):
    s3.put_object(Bucket=BUCKET, Key="records/live-1.json", Body=b"{}")  # a live record, not ours
    records = generate_seeded_records()
    result = upload_seeded_records(s3, BUCKET)
    assert result.written == len(records) and result.deleted == 0
    seeded = {k for k in _keys(s3) if k.startswith(SEEDED_PREFIX)}
    assert SEEDED_PREFIX == "records-seeded/"
    assert seeded == {f"records-seeded/{r['record_id']}.json" for r in records}
    assert _keys(s3) - seeded == {"records/live-1.json"}
    body = json.loads(s3.get_object(Bucket=BUCKET, Key=f"records-seeded/{records[0]['record_id']}.json")["Body"].read())
    assert parse_record(body).record_id == records[0]["record_id"]


def test_rerunning_the_upload_replaces_the_previous_set(s3):
    upload_seeded_records(s3, BUCKET)
    s3.put_object(Bucket=BUCKET, Key="records-seeded/SEED-OLD.json", Body=b"{}")
    s3.put_object(Bucket=BUCKET, Key="records/live-1.json", Body=b"{}")
    small = _small_set()
    result = upload_seeded_records(s3, BUCKET, records=small)
    assert result.written == 5
    assert {k for k in _keys(s3) if k.startswith(SEEDED_PREFIX)} == \
        {f"records-seeded/{r['record_id']}.json" for r in small}
    assert "records/live-1.json" in _keys(s3)  # live records are never touched


def test_an_invalid_record_writes_nothing(s3):
    upload_seeded_records(s3, BUCKET, records=_small_set())
    before = {k: s3.get_object(Bucket=BUCKET, Key=k)["Body"].read() for k in _keys(s3)}
    records = generate_seeded_records()
    declined = next(r for r in records if r["status"] == "declined")
    declined["summary_original"] = "[Synthetic] narrative on a declined record"
    with pytest.raises(ValidationError):
        upload_seeded_records(s3, BUCKET, records=records)
    after = {k: s3.get_object(Bucket=BUCKET, Key=k)["Body"].read() for k in _keys(s3)}
    assert after == before
