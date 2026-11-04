"""Conversation state (issue #13, shared contract) and where it is kept between requests.

Spec: "Conversation state". The agent rebuilds this from the store on every request and never relies
on in-process state. The record (#26) is built from this state, not from the raw transcript.
"""
import json
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from fex.conversation.contract import (
    Answer, ConsentScope, Evidence, FeedbackValue, HistoryEntry, Step,
)
from fex.models import ChallengeTag, Claim


class Profile(BaseModel):
    """Loaded once at start through a scoped lookup on the request's producer ID."""

    producer_id: str
    country: str | None = None
    region: str | None = None
    crop: str | None = None
    entity_type: str | None = None


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


class EarlierAnswer(BaseModel):
    insights: list[Claim]
    peer_examples: list[Claim]
    evidence: Evidence | None = None
    reason: Literal["reopened", "interrupted"]


class ConsentChoice(BaseModel):
    scope: ConsentScope
    at: datetime


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
    partial: ShownClaims | None = Field(default=None, description="Claims shown in an answer that has not finished")
    answer_failed: bool = False
    earlier_answers: list[EarlierAnswer] = Field(default_factory=list)
    consent: ConsentScope | None = None
    consent_history: list[ConsentChoice] = Field(default_factory=list)
    feedback: FeedbackValue | None = None
    evidence_sources: list[str] = Field(default_factory=list, description="Sources tools returned this session")
    history: list[HistoryEntry] = Field(default_factory=list)
    closed_reason: Literal["end", "inactivity", "max_lifetime"] | None = None
    started_at: datetime
    updated_at: datetime

    @property
    def effective_entity_type(self) -> str | None:
        return self.entity_type or self.profile.entity_type


class StateStore(Protocol):
    """Keyed by (producer ID, conversation ID), both from the request context.
    AgentCore Memory implements this in production (memory spec); tests use InMemoryStateStore."""

    def load(self, producer_id: str, conversation_id: str) -> ConversationState | None: ...

    def save(self, state: ConversationState) -> None: ...


class InMemoryStateStore:
    """Keeps state as JSON text, so every request rebuilds it, as it will from AgentCore Memory."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def load(self, producer_id: str, conversation_id: str) -> ConversationState | None:
        raw = self._data.get((producer_id, conversation_id))
        return ConversationState.model_validate(json.loads(raw)) if raw else None

    def save(self, state: ConversationState) -> None:
        self._data[(state.producer_id, state.conversation_id)] = state.model_dump_json()

    def raw(self, producer_id: str, conversation_id: str) -> str | None:
        return self._data.get((producer_id, conversation_id))
