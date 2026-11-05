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

from fex.conversation.contract import ActionEntry, SpokenEntry
from fex.conversation.state import ConversationState
from fex.models import CompletedRecord, DeclinedRecord, PiiScanState, TextScanStatus, decision_refs, parse_record
from fex.pii import PiiText, scan_texts

log = logging.getLogger(__name__)

# Fields that change on every save; they don't count when deciding whether anything changed.
_SAVE_FIELDS = {"updated_at", "version", "created_at"}


def producer_texts(state: ConversationState) -> list[tuple[int, PiiText]]:
    """The texts the record keeps, in history order: the producer's messages and the correct-playback
    text (issue #20). Out-of-scope history positions are skipped: a grievance adds nothing, not even
    a scan error. Each text carries its scan status from the conversation state.
    """
    tracked = {t.history_index: t for t in (state.pii.per_text if state.pii else [])}
    texts: list[tuple[int, PiiText]] = []
    for i, entry in enumerate(state.history):
        if i in state.excluded_history:
            continue
        if isinstance(entry, SpokenEntry) and entry.role == "producer":
            kind, raw = "message", entry.text
        elif isinstance(entry, ActionEntry) and entry.name == "correct_playback":
            kind, raw = "correct_playback", str(entry.args.get("text") or "")
        else:
            continue
        if not raw.strip():
            continue
        texts.append((i, PiiText(text=raw, message_at=entry.at, kind=kind,
                                 status=tracked[i].status if i in tracked else "pending")))
    return texts


def run_pii_scan(state: ConversationState, scanner) -> None:
    """Scan this conversation's producer texts during a save (issue #20) and update `state.pii`.

    A declined record keeps no narrative content, so a declined conversation is not scanned; the
    accumulated state is kept in case consent comes back. An unconfigured scanner (None) changes
    nothing: a missing configuration is not a failed scan.
    """
    if state.consent is None or state.consent == "declined":
        return
    texts = producer_texts(state)
    result = scan_texts(
        [t for _, t in texts], state.language, scanner,
        prior_flag=state.pii.flagged if state.pii else False,
        prior_entity_types=state.pii.entity_types if state.pii else [],
        prior_matches=state.pii.matches if state.pii else [],
    )
    state.pii = PiiScanState(
        per_text=[TextScanStatus(history_index=i, at=t.message_at, kind=t.kind, status=t.status)
                  for i, t in texts],
        flagged=result.flag, entity_types=result.entity_types,
        matches=result.matches, check=result.check,
    )


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
    pii = ({} if state.pii is None else {
        "pii_flag": state.pii.flagged,
        "pii_entity_types": state.pii.entity_types,
        "pii_matches": state.pii.matches,
        "pii_check": state.pii.check,
    })
    return parse_record({
        **common,
        "status": "completed",
        **pii,
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
        # Conversations saved before refs were filtered (#156) can hold non-ID refs; they never reach the record.
        "decision_log": [{**e.model_dump(), "refs": decision_refs(e.refs)} for e in state.decision_log],
    })


def _content_hash(record: CompletedRecord | DeclinedRecord) -> str:
    data = record.model_dump(mode="json", exclude=_SAVE_FIELDS)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------------------------------------- save

def save_record(state: ConversationState, store: RecordStore, now: datetime,
                pii_scanner=None) -> SaveResult | None:
    """Save this conversation's record if it changed. Updates `state` with the saved version.

    Runs the PII scan (`pii_scanner`, issue #20) first so the built record carries the current
    flag, types, matches and check. Returns None when there is nothing to save or nothing changed
    (no write). Raises ValidationError for an invalid record and RecordConflict when a condition
    fails; in both cases nothing is written.
    """
    if pii_scanner is not None:
        run_pii_scan(state, pii_scanner)
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


__all__ = ["DynamoRecordStore", "RecordConflict", "RecordStore", "SaveResult", "build_record",
           "producer_texts", "run_pii_scan", "save_record"]
