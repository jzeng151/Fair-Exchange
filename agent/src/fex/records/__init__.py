"""Write-back (issue #26): build the record from the conversation state and save it with checks.

Spec: docs/specs/26-write-back.md.
  - Code saves the record at fixed points (set_consent, set_feedback, end, auto_close); the model has no save tool.
  - One record per conversation: record_id is the conversation ID.
  - Every save validates with the record models first. An invalid record is an error, not a partial write.
  - A create is conditioned on the record not existing. An update is conditioned on the stored version
    matching the version this conversation last saved, and on the stored producer_id matching the request's.
    A failed condition is a RecordConflict: logged and surfaced, never retried.
"""
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from botocore.exceptions import ClientError

from fex.conversation.state import ConversationState
from fex.models import CompletedRecord, DeclinedRecord, parse_record

log = logging.getLogger(__name__)

# Fields that change on every save; they don't count when deciding whether anything changed.
_SAVE_FIELDS = {"updated_at", "version", "created_at"}


class RecordConflict(Exception):
    """The stored record is not the one this conversation last saved (or belongs to another producer)."""


class RecordStore(Protocol):
    def create(self, record: CompletedRecord | DeclinedRecord) -> None: ...

    def update(self, record: CompletedRecord | DeclinedRecord, expected_version: int) -> None: ...

    def get(self, record_id: str) -> dict | None: ...


@dataclass(frozen=True)
class SaveResult:
    status: str
    consent_scope: str | None
    version: int


# ------------------------------------------------------------------------------------------ build

def build_record(state: ConversationState, *, version: int, created_at: datetime,
                 now: datetime) -> CompletedRecord | DeclinedRecord | None:
    """The record for this conversation's current state, or None when there is nothing to save yet.

    Nothing is built before the producer's first consent choice, or while a reopened playback waits for a
    new one: both cases are "Not decided" in the spec, so nothing is assumed.
    """
    if state.consent is None or not state.consent_history:
        return None
    common: dict[str, Any] = {
        "record_id": state.conversation_id,
        "producer_id": state.producer_id,
        "created_at": created_at,
        "updated_at": now,
        "version": version,
        "closed_at": state.closed_at,
        "consent_history": [c.model_dump() for c in state.consent_history],
    }
    latest = state.consent_history[-1].recorded_at
    if state.consent == "declined":
        return parse_record({**common, "status": "declined", "consent": {"scope": "declined", "recorded_at": latest}})

    playback, answer = state.playback, state.answer
    if playback is None or answer is None:
        return None
    return parse_record({
        **common,
        "status": "completed",
        "consent": {"scope": state.consent, "recorded_at": latest},
        "language": state.language,
        "entity_type": state.effective_entity_type or "unknown",
        "summary_original": playback.summary_original,
        "summary_english": playback.summary_english,
        "tags": playback.tags,
        "evidence": answer.evidence,
        "insights": [c.model_dump() for c in answer.insights],
        "peer_examples": [c.model_dump() for c in answer.peer_examples],
        "earlier_answers": [a.model_dump() for a in state.earlier_answers],
        "feedback": state.feedback,
        # PII flagging (#20): scanned into state before each save; declined records (above) keep none of it
        "pii_flag": state.pii_flag,
        "pii_entity_types": state.pii_entity_types,
        "pii_matches": [m.model_dump() for m in state.pii_matches],
        "pii_check": state.pii_check,
    })


def _content_hash(record: CompletedRecord | DeclinedRecord) -> str:
    data = record.model_dump(mode="json", exclude=_SAVE_FIELDS)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------------------------------------- save

def save_record(state: ConversationState, store: RecordStore, now: datetime) -> SaveResult | None:
    """Save this conversation's record if it changed. Updates `state` with the saved version.

    Returns None when there is nothing to save or nothing changed (no write). Raises ValidationError for
    an invalid record and RecordConflict when a condition fails; in both cases nothing is written.
    """
    first = state.record_version is None
    version = 1 if first else state.record_version + 1
    created_at = now if first else state.record_created_at
    record = build_record(state, version=version, created_at=created_at, now=now)
    if record is None:
        return None
    digest = _content_hash(record)
    if digest == state.record_hash:
        return None
    if first:
        store.create(record)
    else:
        store.update(record, expected_version=state.record_version)
    state.record_version, state.record_created_at, state.record_hash = version, created_at, digest
    return SaveResult(status=record.status, consent_scope=record.consent.scope, version=version)


# -------------------------------------------------------------------------------------- DynamoDB

def _to_item(record: CompletedRecord | DeclinedRecord) -> dict:
    return record.model_dump(mode="json")


def _from_item(item: dict) -> dict:
    return json.loads(json.dumps(item, default=lambda v: int(v) if isinstance(v, Decimal) and v % 1 == 0 else float(v)))


class DynamoRecordStore:
    """The records table: partition key `record_id` (KMS-encrypted, Streams on; defined in CDK, #5/#28).
    The agent runtime role may read and write only this table."""

    def __init__(self, table: Any) -> None:
        self.table = table

    def create(self, record: CompletedRecord | DeclinedRecord) -> None:
        self._put(record, ConditionExpression="attribute_not_exists(record_id)")

    def update(self, record: CompletedRecord | DeclinedRecord, expected_version: int) -> None:
        self._put(record, ConditionExpression="version = :expected AND producer_id = :owner",
                  ExpressionAttributeValues={":expected": expected_version, ":owner": record.producer_id})

    def get(self, record_id: str) -> dict | None:
        item = self.table.get_item(Key={"record_id": record_id}).get("Item")
        return _from_item(item) if item else None

    def _put(self, record: CompletedRecord | DeclinedRecord, **condition: Any) -> None:
        try:
            self.table.put_item(Item=_to_item(record), **condition)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                log.error("record %s: conditional write failed (version %s)", record.record_id, record.version)
                raise RecordConflict(record.record_id) from exc
            raise


__all__ = ["DynamoRecordStore", "RecordConflict", "RecordStore", "SaveResult", "build_record", "save_record"]
