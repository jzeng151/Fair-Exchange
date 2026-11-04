"""Reads of the records table. Always strongly consistent: the stream event is only a signal."""
import os
from collections.abc import Callable, Iterator
from typing import Any

import boto3

from .publish import RECORDS_PREFIX


def table_name() -> str:
    return os.environ["RECORDS_TABLE"]


def bucket_name() -> str:
    return os.environ["SYNC_BUCKET"]


def reader(table, record_id: str) -> Callable[[], dict[str, Any] | None]:
    """A function that does a fresh consistent read of one record, or returns None if it is gone."""
    def read_current() -> dict[str, Any] | None:
        return table.get_item(Key={"record_id": record_id}, ConsistentRead=True).get("Item")
    return read_current


def scan_record_ids(table) -> Iterator[str]:
    """Record IDs only. Callers must re-read each record; the scanned data is never published."""
    kwargs: dict[str, Any] = {"ProjectionExpression": "record_id"}
    while True:
        page = table.scan(**kwargs)
        for item in page["Items"]:
            yield item["record_id"]
        if "LastEvaluatedKey" not in page:
            return
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def list_object_record_ids(s3, bucket: str) -> Iterator[str]:
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=RECORDS_PREFIX):
        for obj in page.get("Contents", []):
            name = obj["Key"].removeprefix(RECORDS_PREFIX)
            if name.endswith(".json"):
                yield name.removesuffix(".json")


def default_table():
    return boto3.resource("dynamodb").Table(table_name())


def default_s3():
    return boto3.client("s3")
