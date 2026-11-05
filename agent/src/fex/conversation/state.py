"""Conversation state (issue #13, shared contract) and where it is kept between requests.

Spec: "Conversation state". The agent rebuilds this from the store on every request and never relies
on in-process state. The record (#26) is built from this state, not from the raw transcript.
"""
import json
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from fex.models import PiiScanState  # noqa: F401  (re-exported so state round-trips keep the type)

from fex.conversation.contract import (
    Answer, ConsentScope, Evidence, FeedbackValue, HistoryEntry, Step,
)
from fex.models import ChallengeTag, Claim, ConsentChoice, EarlierAnswer, DecisionLogEntry
from fex.verifier import SessionEvidence, SourceKind


class Profile(BaseModel):
    """Loaded once at start through a scoped lookup on the request's producer ID."""

    producer_id: str
    country: str | None = None
    region: str | None = None
    crop: str | None = None
    entity_type: str | None = None
    language: str | None = Field(default=None, description="ISO 639-1 code, if the profile has one (#22)")


class Playback(BaseModel):
    """What FEX understood. Summaries and tags are filled in at confirm_playback."""

    text: str
    challenge: str
    timing: str
    severity: str
    tried: str
    summary_original: str | None = None
    summary_english: str | None = None
    tags: list[ChallengeTag] = Field(default_factory=list)
    confirmed: bool = False


class ShownClaims(BaseModel):
    """Claims already sent to the producer during an answer that has not finished."""

    insights: list[Claim] = Field(default_factory=list)
    peer_examples: list[Claim] = Field(default_factory=list)


class ConversationState(BaseModel):
    producer_id: str
    conversation_id: str
    step: Step = "intake"
    language: str = "en"
    profile: Profile
    entity_type: str | None = Field(default=None, description="Corrected entity type, if the producer gave one")
    location_note: str | None = Field(default=None, description="Set when the producer disputes the location on file")
    playback: Playback | None = None
    answer: Answer | None = None
    answer_given_at: datetime | None = None
    partial: ShownClaims | None = Field(default=None, description="Claims shown in an answer that has not finished")
    partial_started_at: datetime | None = None
    answer_failed: bool = False
    earlier_answers: list[EarlierAnswer] = Field(default_factory=list)
    consent: ConsentScope | None = None
    consent_history: list[ConsentChoice] = Field(default_factory=list)
    feedback: FeedbackValue | None = None
    evidence_sources: dict[str, SourceKind] = Field(
        default_factory=dict, description="Source label -> kind, for every item the data tools returned (#17)")
    evidence_clauses: list[str] = Field(default_factory=list, description="Clause IDs the standards tool returned")
    decision_log: list[DecisionLogEntry] = Field(default_factory=list)
    history: list[HistoryEntry] = Field(default_factory=list)
    pii: PiiScanState | None = Field(
        default=None, description="PII scan tracking (#20): per-text status plus the accumulated flag, "
                                  "types and matches that the record's pii fields carry on the next save")
    excluded_history: list[int] = Field(
        default_factory=list, description="History positions of out-of-scope exchanges (#21): shown on resume, "
                                          "never given to a model, so they can't reach the playback or record")
    closed_reason: Literal["end", "inactivity", "max_lifetime"] | None = None
    closed_at: datetime | None = None
    # Write-back (#26): what this conversation last saved, for conditional updates and no-op detection
    record_version: int | None = None
    record_created_at: datetime | None = None
    record_hash: str | None = None
    started_at: datetime
    updated_at: datetime
    revision: int = Field(default=0, description="Increases on every save; a save must match the revision it loaded")

    @property
    def effective_entity_type(self) -> str | None:
        return self.entity_type or self.profile.entity_type

    def session_evidence(self) -> SessionEvidence:
        return SessionEvidence(sources=dict(self.evidence_sources), clauses=set(self.evidence_clauses))

    def keep_evidence(self, evidence: SessionEvidence) -> None:
        self.evidence_sources = dict(sorted(evidence.sources.items()))
        self.evidence_clauses = sorted(evidence.clauses)


class StateConflict(Exception):
    """The stored state changed since this request loaded it. The chat API's turn lock (#25) should make this
    impossible; if it happens, the stale request must not overwrite the newer state."""


class StateStore(Protocol):
    """Keyed by (producer ID, conversation ID), both from the request context.
    AgentCore Memory implements this in production (memory spec); tests use InMemoryStateStore.

    `save` must reject the write with StateConflict unless the stored revision equals `expected_revision`
    (None: the conversation must not exist yet), then store the state with its revision increased by one."""

    def load(self, producer_id: str, conversation_id: str) -> ConversationState | None: ...

    def save(self, state: ConversationState, expected_revision: int | None) -> None: ...


class InMemoryStateStore:
    """Keeps state as JSON text, so every request rebuilds it, as it will from AgentCore Memory."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def load(self, producer_id: str, conversation_id: str) -> ConversationState | None:
        raw = self._data.get((producer_id, conversation_id))
        return ConversationState.model_validate(json.loads(raw)) if raw else None

    def save(self, state: ConversationState, expected_revision: int | None) -> None:
        key = (state.producer_id, state.conversation_id)
        current = self._data.get(key)
        stored = None if current is None else ConversationState.model_validate(json.loads(current)).revision
        if stored != expected_revision:
            raise StateConflict(f"conversation {state.conversation_id}: stored revision {stored}, "
                                f"expected {expected_revision}")
        state.revision = 0 if expected_revision is None else expected_revision + 1
        self._data[key] = state.model_dump_json()

    def raw(self, producer_id: str, conversation_id: str) -> str | None:
        return self._data.get((producer_id, conversation_id))
