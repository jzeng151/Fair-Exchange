"""Shared scope helpers: the ONLY way a data tool learns who the producer is and what was confirmed.

Everything comes from the invocation state the engine builds from the conversation state, in code.
The model can call a data tool but cannot set any of it (docs/specs/17-standards-grounding.md).
"""
from typing import Any

RETRIEVAL_STEP = "respond"
REFUSAL = {"refused": True, "reason": "Data tools run only after the producer confirms the playback."}


def session_producer_id(state: dict[str, Any]) -> str:
    producer_id = state.get("producer_id")
    if not producer_id:
        raise PermissionError("No producer in session")
    return producer_id


def retrieval_refusal(state: dict[str, Any]) -> dict | None:
    """Step gating (#13): data tools run only in `respond`. Returns the refusal result, or None to proceed.
    The step comes from the conversation state in code, never from the model."""
    if state.get("step") != RETRIEVAL_STEP:
        return dict(REFUSAL)
    return None


def session_entity_type(state: dict[str, Any]) -> str | None:
    """Entity type the producer corrected in playback (#13). Not a scope field; used for peer matching."""
    return state.get("entity_type") or None


def session_tags(state: dict[str, Any]) -> list[str]:
    """The confirmed challenge tags (#13)."""
    return list(state.get("tags") or [])
