"""Per-session inputs the evaluators read (spec [36](https://github.com/jzeng151/Fair-Exchange/issues/36),
[34](https://github.com/jzeng151/Fair-Exchange/issues/34), [17](https://github.com/jzeng151/Fair-Exchange/issues/17)).

The eval stack's records table (write-back [#26](https://github.com/jzeng151/Fair-Exchange/issues/26),
one record, `record_id` = conversation ID) and the eval evidence bucket (capture [#34](https://github.com/jzeng151/Fair-Exchange/issues/34),
one JSON object per conversation ID) feed each evaluator with the record the conversation saved
and the evidence the conversation emitted: every tool result item, every emitted claim, the
dropped-claim reason codes and the final step.

AWS-only: loaders use boto3 against DynamoDB + S3, `us-west-2`. A `SessionDirectory` gives the
same data from plain dicts, so the unit tests and the offline report are hermetic.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from typing import Any, Protocol

from fex.models import CompletedRecord, DeclinedRecord, parse_record
from pydantic import BaseModel, ConfigDict, Field

RECORDS_TABLE_ENV = "EVAL_RECORDS_TABLE"  # DynamoDB table, partition key `record_id` (#26)
EVIDENCE_BUCKET_ENV = "EVAL_EVIDENCE_BUCKET"  # bucket with one capture per conversation ID (#34)


EvidencePayload = dict[str, Any]


class EvalEvidence(BaseModel):
    """The evidence the runtime captured for one conversation ([#34](https://github.com/jzeng151/Fair-Exchange/issues/34) shared contract)."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1)
    final_step: str = Field(min_length=1)
    tool_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Every tool result item: {tool, source, data}, citable source labels included (#17)",
    )
    clauses: list[str] = Field(
        default_factory=list,
        description="The standards tool's returned clause IDs for this conversation (#17)",
    )
    claims: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Every emitted claim: {kind: 'insight' | 'peer_example', text, citation}",
    )
    dropped: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Dropped claims: {text, reason_code} from the verifier's reason codes (#17)",
    )

    def tool_sources(self, tool_names: Iterable[str] | None = None) -> set[str]:
        """The citable source labels the given tools returned in this conversation."""
        if tool_names is None:
            return {item["source"] for item in self.tool_items if item.get("source")}
        return {
            item["source"]
            for item in self.tool_items
            if item.get("source") and item.get("tool") in tool_names
        }


class Session(BaseModel):
    """One evaluated conversation: the record it saved plus the evidence it emitted."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    session_id: str = Field(min_length=1, description="Record ID = conversation ID (#26)")
    record: CompletedRecord | DeclinedRecord
    evidence: EvalEvidence | None = Field(
        default=None,
        description="None when evalAccess was off: only the non-evidence evaluators run",
    )


class ReferenceData(BaseModel):
    """Reference inputs for one conversation (spec 36: AgentCore Evaluations reference inputs)."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    reference_tags: list[str] = Field(
        default_factory=list, description="Human tag labels for the tagged accounts (#35)")
    forbidden: list[str] = Field(
        default_factory=list,
        description="Scope-leak needles: another producer's IDs, region and organization (#34)")

    def filled(self) -> bool:
        return bool(self.reference_tags or self.forbidden)


class RecordStore(Protocol):
    """Read-only record lookups by conversation ID ([#26](https://github.com/jzeng151/Fair-Exchange/issues/26))."""

    def get(self, session_id: str) -> CompletedRecord | DeclinedRecord:
        ...  # pragma: no cover - protocol


class EvidenceStore(Protocol):
    """Read-only evidence capture lookups by conversation ID ([#34](https://github.com/jzeng151/Fair-Exchange/issues/34))."""

    def get(self, session_id: str) -> EvalEvidence | None:
        ...  # pragma: no cover - protocol


class DynamoRecordStore:
    """Reads the eval stack's records table. The evaluators never write."""

    def __init__(self, table_name: str, region: str = "us-west-2", client: Any = None):
        if client is None:
            import boto3  # AWS-only: the sandbox's Bedrock-side client is fine here
            client = boto3.client("dynamodb", region_name=region)
        self._table_name = table_name
        self._client = client

    def get(self, session_id: str) -> CompletedRecord | DeclinedRecord:
        response = self._client.get_item(
            TableName=self._table_name, Key={"record_id": {"S": session_id}})
        item = response.get("Item")
        if not item:
            raise LookupError(f"no record for conversation {session_id}")
        return parse_record(_from_dynamo(item))


class S3EvidenceStore:
    """Reads one evidence capture per conversation ID from the eval evidence bucket ([#34](https://github.com/jzeng151/Fair-Exchange/issues/34))."""

    def __init__(self, bucket_name: str, region: str = "us-west-2", client: Any = None):
        if client is None:
            import boto3
            client = boto3.client("s3", region_name=region)
        self._bucket = bucket_name
        self._client = client

    def get(self, session_id: str) -> EvalEvidence | None:
        import botocore.exceptions
        try:
            body = self._client.get_object(Bucket=self._bucket, Key=session_id)["Body"]
        except botocore.exceptions.ClientError as error:
            # get_object raises ClientError (code NoSuchKey / NotFound), never the
            # NoSuchKey class: treat ONLY those codes as missing evidence (evalAccess
            # was off or the capture expired); any other S3 error fails the run.
            code = error.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "NotFound", "404"):
                return None
            raise
        return EvalEvidence.model_validate(json.loads(body.read()))


class SessionDirectory:
    """In-memory stores for offline runs: the unit tests and the report builder use this."""

    def __init__(
        self,
        records: dict[str, CompletedRecord | DeclinedRecord | EvidencePayload] | None = None,
        evidence: dict[str, EvalEvidence | EvidencePayload | None] | None = None,
    ):
        self._records = {
            _key(k): (v if isinstance(v, (CompletedRecord, DeclinedRecord))
                      else parse_record(v))
            for k, v in (records or {}).items()
        }
        self._evidence = {
            _key(k): (v if v is None or isinstance(v, EvalEvidence)
                      else EvalEvidence.model_validate(v))
            for k, v in (evidence or {}).items()
        }

    def add_record(self, session_id: str, record: dict[str, Any] | CompletedRecord
                   | DeclinedRecord) -> None:
        self._records[_key(session_id)] = (
            record if isinstance(record, (CompletedRecord, DeclinedRecord))
            else parse_record(record))

    def add_evidence(self, session_id: str, payload: EvidencePayload | EvalEvidence | None
                     ) -> None:
        self._evidence[_key(session_id)] = (
            payload if payload is None or isinstance(payload, EvalEvidence)
            else EvalEvidence.model_validate(payload))

    def get_record(self, session_id: str) -> CompletedRecord | DeclinedRecord:
        try:
            return self._records[_key(session_id)]
        except KeyError:  # same failure shape as DynamoDB: the conversation saved no record
            raise LookupError(f"no record for conversation {session_id}") from None

    def get_evidence(self, session_id: str) -> EvalEvidence | None:
        return self._evidence.get(_key(session_id))


EnvDirectory = SessionDirectory  # descriptive name for offline runs


def load_sessions(
    session_ids: Iterable[str],
    records: RecordStore,
    evidence: EvidenceStore,
) -> Iterator[Session]:
    for session_id in session_ids:
        yield Session(
            session_id=session_id,
            record=records.get(session_id),
            evidence=evidence.get(session_id),
        )


def _key(session_id: str) -> str:
    return session_id


def _from_dynamo(item: dict[str, Any]) -> dict[str, Any]:
    """DynamoDB AttributeValue -> plain JSON record (Decimal-safe)."""
    import decimal

    def _plain(value: Any) -> Any:
        if isinstance(value, dict):
            if "S" in value:
                return value["S"]
            if "N" in value:
                return int(value["N"]) if _is_int(value["N"]) else float(value["N"])
            if "M" in value:
                return {k: _plain(v) for k, v in value["M"].items()}
            if "L" in value:
                return [_plain(v) for v in value["L"]]
            if "BOOL" in value:
                return value["BOOL"]
            if "NULL" in value:
                return None
        return value

    def _as_json(value: Any) -> Any:
        if isinstance(value, decimal.Decimal):
            _number(value)
        if isinstance(value, dict):
            return {k: _as_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_as_json(v) for v in value]
        return value

    def _is_int(text: str) -> bool:
        try:
            int(text)
            return "." not in text and "e" not in text.lower()
        except ValueError:
            return False

    def _number(value: decimal.Decimal) -> Any:
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    return _as_json({k: _plain(v) for k, v in item.items()})


def records_table_from_env(region: str = "us-west-2") -> DynamoRecordStore:
    table_name = os.environ.get(RECORDS_TABLE_ENV)
    if not table_name:
        raise AssertionError(f"{RECORDS_TABLE_ENV} names the eval stack's records table")
    return DynamoRecordStore(table_name, region=region)


def evidence_bucket_from_env(region: str = "us-west-2") -> S3EvidenceStore:
    bucket_name = os.environ.get(EVIDENCE_BUCKET_ENV)
    if not bucket_name:
        raise AssertionError(f"{EVIDENCE_BUCKET_ENV} names the eval stack's evidence bucket")
    return S3EvidenceStore(bucket_name, region=region)