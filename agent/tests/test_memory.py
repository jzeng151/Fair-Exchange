"""Persistent conversation memory (docs/specs/memory.md, #59), seam 1.

Drives the AgentCore-Memory-backed StateStore the way the chat API does, through an in-memory memory
stand-in behind the same interface (FakeMemoryClient). Cases are the spec's Testing Decisions list.
"""
from datetime import UTC, datetime

import pytest
from tests.conversation_harness import STANDARDS, FakeMemoryClient, cauca_producer, intake, playback

from fex.conversation import (
    AgentCoreMemoryStateStore, ConversationEngine, RetentionConfig, producer_namespace, recall_eligibility,
)
from fex.conversation.state import ConversationState, Profile, StateConflict

MEMORY_ID = "mem-test"


def _store() -> AgentCoreMemoryStateStore:
    return AgentCoreMemoryStateStore(MEMORY_ID, FakeMemoryClient())


def _state(producer_id: str, conversation_id: str, **over) -> ConversationState:
    now = datetime(2026, 11, 4, 12, tzinfo=UTC)
    base = dict(producer_id=producer_id, conversation_id=conversation_id,
                profile=Profile(producer_id=producer_id), started_at=now, updated_at=now)
    base.update(over)
    return ConversationState(**base)


# ---------------------------------------------------------------- store round-trip & concurrency

def test_save_then_load_round_trips_state():
    store = _store()
    store.save(_state("P1", "c1", step="playback", language="es"), expected_revision=None)
    loaded = store.load("P1", "c1")
    assert loaded is not None
    assert (loaded.step, loaded.language, loaded.revision) == ("playback", "es", 0)


def test_load_unknown_conversation_is_none():
    assert _store().load("P1", "nope") is None


def test_save_increments_revision_and_rejects_stale_writes():
    store = _store()
    store.save(_state("P1", "c1"), expected_revision=None)  # revision 0
    store.save(_state("P1", "c1"), expected_revision=0)  # revision 1
    assert store.load("P1", "c1").revision == 1
    # A request that loaded revision 0 must not overwrite revision 1.
    with pytest.raises(StateConflict):
        store.save(_state("P1", "c1"), expected_revision=0)


def test_create_requires_no_existing_conversation():
    store = _store()
    store.save(_state("P1", "c1"), expected_revision=None)
    with pytest.raises(StateConflict):
        store.save(_state("P1", "c1"), expected_revision=None)


def test_load_returns_the_newest_state_past_one_page_of_events():
    # One event per save; more saves than a page must still read the latest state, not a stale one.
    store = _store()
    store.save(_state("P1", "c1"), expected_revision=None)  # revision 0
    pages = AgentCoreMemoryStateStore._PAGE
    for rev in range(pages + 5):  # well past a single page of events
        store.save(_state("P1", "c1", step="playback"), expected_revision=rev)
    loaded = store.load("P1", "c1")
    assert loaded.revision == pages + 5  # the newest revision, not the event at the page boundary
    assert loaded.step == "playback"


def test_delete_removes_every_event_past_one_page():
    store = _store()
    store.save(_state("P1", "c1"), expected_revision=None)
    pages = AgentCoreMemoryStateStore._PAGE
    for rev in range(pages + 5):
        store.save(_state("P1", "c1"), expected_revision=rev)
    deleted = store.delete_conversation("P1", "c1")
    assert deleted == pages + 6  # the create plus every update
    assert store.load("P1", "c1") is None


# ---------------------------------------------------------------- resume after the agent is discarded

def test_resume_after_agent_discarded_returns_same_history_step_actions_and_state():
    client = FakeMemoryClient()  # survives the engine; the runtime is recycled, memory is not
    producer, conv = cauca_producer(), "c-resume"

    def build_engine():
        from tests.conversation_harness import ScriptedModel
        return ConversationEngine(store=AgentCoreMemoryStateStore(MEMORY_ID, client),
                                  small_model=ScriptedModel(), large_model=ScriptedModel(), standards=STANDARDS)

    first = build_engine()
    first.small_model.add(intake("¿Qué ha sido difícil?"), intake("", ready=True), playback())
    first.handle({"kind": "start", "producerId": producer, "conversationId": conv})
    first.handle({"kind": "message", "producerId": producer, "conversationId": conv,
                  "text": "La lluvia bajó mucho."})
    before = AgentCoreMemoryStateStore(MEMORY_ID, client).load(producer, conv)

    # The agent object is thrown away; a fresh engine is rebuilt from memory on the next request.
    del first
    resumed = build_engine().handle({"kind": "resume", "producerId": producer, "conversationId": conv})

    assert resumed.step == before.step
    assert [h.model_dump() for h in resumed.history] == [h.model_dump() for h in before.history]
    after = AgentCoreMemoryStateStore(MEMORY_ID, client).load(producer, conv)
    assert after.model_dump() == before.model_dump()


# ---------------------------------------------------------------- cross-producer isolation

def test_load_never_returns_another_producers_state_even_when_text_mentions_them():
    store = _store()
    # Producer B's conversation mentions producer A by id in the text.
    store.save(_state("B", "cb", location_note="talking about A here"), expected_revision=None)
    store.save(_state("A", "ca"), expected_revision=None)
    # A read for A, with A's own id, never reaches B's conversation under B's actor id.
    assert store.load("A", "cb") is None
    assert store.load("A", "ca").producer_id == "A"


def test_producer_namespace_is_scoped_to_the_actor():
    assert producer_namespace("A") == "/actor/A/"
    assert producer_namespace("A") != producer_namespace("B")


# ---------------------------------------------------------------- recall switched off

def test_recall_eligibility_returns_nothing_while_switched_off():
    assert recall_eligibility("A", "any query") == []


# ---------------------------------------------------------------- deletion scoped to one conversation

def test_delete_conversation_removes_only_that_conversations_events():
    store = _store()
    store.save(_state("P1", "c1"), expected_revision=None)
    store.save(_state("P1", "c1"), expected_revision=0)
    store.save(_state("P1", "c2"), expected_revision=None)
    store.save(_state("P2", "c1"), expected_revision=None)  # another producer, same conversation id

    deleted = store.delete_conversation("P1", "c1")

    assert deleted == 2
    assert store.load("P1", "c1") is None
    assert store.load("P1", "c2") is not None  # same producer, other conversation untouched
    assert store.load("P2", "c1") is not None  # other producer untouched


# ---------------------------------------------------------------- retention check at startup

def test_retention_rejects_event_expiry_not_longer_than_max_lifetime():
    # 3 days = 4320 minutes. A max lifetime of 4320 minutes is not shorter, so it must be rejected.
    with pytest.raises(ValueError, match="longer than the maximum conversation lifetime"):
        RetentionConfig(event_expiry_days=3, max_lifetime_minutes=4320)


def test_retention_accepts_event_expiry_longer_than_max_lifetime():
    cfg = RetentionConfig(event_expiry_days=3, max_lifetime_minutes=120)
    assert cfg.event_expiry_days == 3 and cfg.max_lifetime_minutes == 120


def test_retention_rejects_event_expiry_outside_agentcore_limits():
    with pytest.raises(ValueError, match="between 3 and 365 days"):
        RetentionConfig(event_expiry_days=2, max_lifetime_minutes=60)
    with pytest.raises(ValueError, match="between 3 and 365 days"):
        RetentionConfig(event_expiry_days=366, max_lifetime_minutes=60)


def test_retention_from_env_is_none_when_unset(monkeypatch):
    monkeypatch.delenv("FEX_EVENT_EXPIRY_DAYS", raising=False)
    monkeypatch.delenv("FEX_MAX_LIFETIME_MINUTES", raising=False)
    assert RetentionConfig.from_env() is None


def test_retention_from_env_builds_and_checks(monkeypatch):
    monkeypatch.setenv("FEX_EVENT_EXPIRY_DAYS", "7")
    monkeypatch.setenv("FEX_MAX_LIFETIME_MINUTES", "120")
    cfg = RetentionConfig.from_env()
    assert cfg is not None and cfg.event_expiry_days == 7


# ---------------------------------------------------------------- runtime wiring

def test_runtime_state_store_is_in_memory_without_memory_id(monkeypatch):
    from fex.conversation import runtime
    from fex.conversation.state import InMemoryStateStore
    monkeypatch.delenv("FEX_MEMORY_ID", raising=False)
    assert isinstance(runtime.state_store(), InMemoryStateStore)


def test_runtime_state_store_rejects_memory_id_without_retention_config(monkeypatch):
    from fex.conversation import runtime
    monkeypatch.setenv("FEX_MEMORY_ID", "mem-abc")
    monkeypatch.delenv("FEX_EVENT_EXPIRY_DAYS", raising=False)
    monkeypatch.delenv("FEX_MAX_LIFETIME_MINUTES", raising=False)
    with pytest.raises(RuntimeError, match="both are required"):
        runtime.state_store()


def test_load_returns_the_newest_state_whatever_order_events_come_back_in():
    # The live ListEvents returns newest first (sandbox, 2026-11-04); the client's docstring says chronological.
    # Taking the last event read the oldest state, so every turn restarted the conversation in intake.
    store = _store()
    store.save(_state("P1", "c1"), expected_revision=None)  # revision 0, intake
    store.save(_state("P1", "c1", step="playback"), expected_revision=0)
    store.save(_state("P1", "c1", step="respond"), expected_revision=1)
    loaded = store.load("P1", "c1")
    assert loaded.revision == 2 and loaded.step == "respond"
    with pytest.raises(StateConflict):  # a save that read the stale state is rejected
        store.save(_state("P1", "c1", step="consent"), expected_revision=0)
