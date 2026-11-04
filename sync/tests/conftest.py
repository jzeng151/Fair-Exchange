import json

import boto3
import pytest
from moto import mock_aws

BUCKET = "sync-bucket"
TABLE = "records"


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("RECORDS_TABLE", TABLE)
    monkeypatch.setenv("SYNC_BUCKET", BUCKET)
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield s3, table


def make_record(record_id="r1", version=1, **overrides):
    record = {
        "record_id": record_id, "producer_id": "p1", "version": version, "status": "completed",
        "consent": {"scope": "internal", "recorded_at": "2026-11-04T10:00:00Z"},
        "language": "en", "entity_type": "cooperative", "summary_original": "Heavy rain hurt the harvest",
        "tags": ["climate and weather"], "review_status": "pending",
    }
    record.update(overrides)
    return record


def stream_event(*record_ids):
    """A keys-only DynamoDB Streams event, as the Lambda receives it."""
    return {"Records": [
        {"eventName": "MODIFY", "dynamodb": {"Keys": {"record_id": {"S": rid}}, "SequenceNumber": f"{i:03d}"}}
        for i, rid in enumerate(record_ids)
    ]}


def stored(s3, record_id):
    """(parsed JSON, metadata) of the object for a record, or None."""
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=f"records/{record_id}.json")
    except s3.exceptions.NoSuchKey:
        return None
    return json.loads(obj["Body"].read()), obj["Metadata"]
