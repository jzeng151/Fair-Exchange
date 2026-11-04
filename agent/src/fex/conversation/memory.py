"""Persistent conversation memory on Amazon Bedrock AgentCore Memory (docs/specs/memory.md, #59).

This module backs the StateStore Protocol (state.py) with AgentCore Memory, so a producer can resume
an unfinished conversation after the browser is closed and the runtime is recycled. It also holds the
recall-eligibility seam for long-term memory and a deletion function for one conversation's short-term
events.

Scope rule (spec #7): the memory keys are always the producer ID (actor) and conversation ID (session)
from the request context. They never come from model output or producer text. The caller passes them;
this module never derives them from anything a model or producer wrote.

Not decided, so not built here (spec "Further Notes"):
  - the retention values (set by configuration: FEX_EVENT_EXPIRY_DAYS, FEX_MAX_LIFETIME_MINUTES);
  - when the deletion function is called;
  - which long-term memories are eligible for recall. `recall_eligibility` returns nothing until the
    decline policy is decided, so recall is built but switched off and declined text cannot resurface.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fex.conversation.state import ConversationState, StateConflict

log = logging.getLogger(__name__)

# One short-term event per saved state. The newest event is the current conversation state; older events
# are the history AgentCore Memory keeps for the long-term strategies. The state's own `revision` field
# carries optimistic concurrency, so a stale request cannot overwrite newer state (same rule as #25/#13).
_STATE_ROLE = "ASSISTANT"


class RetentionConfig:
    """Retention periods for the memory resource. Values are configuration (spec #9); there is no default
    maximum conversation lifetime, so none is invented here.

    The event (short-term) expiry must be longer than the maximum conversation lifetime, so an active
    conversation never outlives its stored messages (spec "Retention"; #13 closing rules). The agent
    refuses to start if this rule is broken.
    """

    # AgentCore allows 3 to 365 days for short-term events.
    MIN_EVENT_EXPIRY_DAYS = 3
    MAX_EVENT_EXPIRY_DAYS = 365

    def __init__(self, event_expiry_days: int, max_lifetime_minutes: int) -> None:
        self.event_expiry_days = event_expiry_days
        self.max_lifetime_minutes = max_lifetime_minutes
        self._check()

    def _check(self) -> None:
        if not (self.MIN_EVENT_EXPIRY_DAYS <= self.event_expiry_days <= self.MAX_EVENT_EXPIRY_DAYS):
            raise ValueError(
                f"FEX_EVENT_EXPIRY_DAYS must be between {self.MIN_EVENT_EXPIRY_DAYS} and "
                f"{self.MAX_EVENT_EXPIRY_DAYS} days (AgentCore limit); got {self.event_expiry_days}")
        if self.max_lifetime_minutes <= 0:
            raise ValueError(f"FEX_MAX_LIFETIME_MINUTES must be positive; got {self.max_lifetime_minutes}")
        # The event expiry counts from the conversation's start and must outlast the whole conversation.
        event_expiry_minutes = self.event_expiry_days * 24 * 60
        if event_expiry_minutes <= self.max_lifetime_minutes:
            raise ValueError(
                f"event expiry ({self.event_expiry_days} days = {event_expiry_minutes} min) must be longer "
                f"than the maximum conversation lifetime ({self.max_lifetime_minutes} min), so an active "
                f"conversation never outlives its stored messages (memory spec, #13)")

    @classmethod
    def from_env(cls) -> "RetentionConfig | None":
        """Build from configuration, or None when either value is unset (local runs without memory)."""
        expiry = os.environ.get("FEX_EVENT_EXPIRY_DAYS")
        lifetime = os.environ.get("FEX_MAX_LIFETIME_MINUTES")
        if not expiry or not lifetime:
            return None
        return cls(event_expiry_days=int(expiry), max_lifetime_minutes=int(lifetime))


def producer_namespace(actor_id: str) -> str:
    """Long-term namespace for one producer, built in code from the request context (never model output).

    Any retrieval reads only the calling producer's namespace, so no producer can reach another's memories
    (spec #6). The namespace template on the memory resource (CDK) mirrors this, keyed on the actor ID.
    """
    return f"/actor/{actor_id}/"


def recall_eligibility(actor_id: str, query: str) -> list[dict[str, Any]]:
    """Which long-term memories may feed intake and playback for this producer.

    Switched off: returns nothing until the decline policy is decided (spec "Recall eligibility"), so
    recalled context cannot leak declined text into a later conversation or record. The one place recall
    is decided lives here, so turning it on is a single, testable change. Recall is never a citable
    source even when on; insights and peer examples come only from the data tools and the citation check.
    """
    return []


class AgentCoreMemoryStateStore:
    """StateStore backed by AgentCore Memory short-term events (spec: "Short-term memory (resume)").

    One conversation's state is stored as a chain of short-term events under (actor=producer_id,
    session=conversation_id). The newest event holds the current ConversationState as JSON. `load`
    reads the newest event; `save` appends a new event after checking the revision, which gives the
    same optimistic-concurrency contract as InMemoryStateStore. AgentCore's long-term strategies read
    these events to extract per-producer summaries and facts under `producer_namespace`.
    """

    def __init__(self, memory_id: str, client: Any) -> None:
        self.memory_id = memory_id
        self.client = client  # bedrock_agentcore.memory.MemoryClient (or a stand-in with the same methods)

    # ------------------------------------------------------------------ StateStore

    def load(self, producer_id: str, conversation_id: str) -> ConversationState | None:
        event = self._latest_event(producer_id, conversation_id)
        if event is None:
            return None
        return ConversationState.model_validate(json.loads(self._state_json(event)))

    def save(self, state: ConversationState, expected_revision: int | None) -> None:
        latest = self._latest_event(state.producer_id, state.conversation_id)
        stored = None if latest is None else ConversationState.model_validate(
            json.loads(self._state_json(latest))).revision
        if stored != expected_revision:
            raise StateConflict(
                f"conversation {state.conversation_id}: stored revision {stored}, expected {expected_revision}")
        state.revision = 0 if expected_revision is None else expected_revision + 1
        self.client.create_event(
            memory_id=self.memory_id,
            actor_id=state.producer_id,
            session_id=state.conversation_id,
            messages=[(state.model_dump_json(), _STATE_ROLE)],
        )

    # ------------------------------------------------------------------ deletion (spec "Deletion function")

    def delete_conversation(self, producer_id: str, conversation_id: str) -> int:
        """Delete one conversation's short-term events, and no other conversation's.

        Covers short-term events only. Whether long-term records can be traced to a single conversation
        is a spike check (spec); until it passes, this makes no promise about long-term records.
        Returns the number of events deleted.
        """
        events = self.client.list_events(
            memory_id=self.memory_id, actor_id=producer_id, session_id=conversation_id, max_results=1000)
        deleted = 0
        for event in events:
            self.client.delete_event(
                memory_id=self.memory_id, actor_id=producer_id, session_id=conversation_id,
                event_id=event["eventId"])
            deleted += 1
        return deleted

    # ------------------------------------------------------------------ internals

    def _latest_event(self, producer_id: str, conversation_id: str) -> dict[str, Any] | None:
        events = self.client.list_events(
            memory_id=self.memory_id, actor_id=producer_id, session_id=conversation_id, max_results=1000)
        if not events:
            return None
        # list_events returns chronological order; the newest event is the current state.
        return events[-1]

    @staticmethod
    def _state_json(event: dict[str, Any]) -> str:
        """Pull the serialized ConversationState out of a short-term event payload."""
        for item in event.get("payload", []):
            conv = item.get("conversational")
            if conv and "content" in conv:
                return conv["content"]["text"]
        raise ValueError(f"event {event.get('eventId')} has no conversational payload")
