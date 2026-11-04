"""Shared scope helpers: the ONLY way a tool learns who the producer is, and whether it may run."""
from strands.types.tools import ToolContext

RETRIEVAL_STEP = "respond"
REFUSAL = {"refused": True, "reason": "Data tools run only after the producer confirms the playback."}


def session_producer_id(tool_context: ToolContext) -> str:
    producer_id = tool_context.invocation_state.get("producer_id")
    if not producer_id:
        raise PermissionError("No producer in session")
    return producer_id


def retrieval_refusal(tool_context: ToolContext) -> dict | None:
    """Step gating (#13): data tools run only in `respond`. Returns the refusal result, or None to proceed.
    The step comes from the conversation state in code, never from the model."""
    if tool_context.invocation_state.get("step") != RETRIEVAL_STEP:
        return dict(REFUSAL)
    return None


def session_entity_type(tool_context: ToolContext) -> str | None:
    """Entity type the producer corrected in playback (#13). Not a scope field; used for peer matching."""
    return tool_context.invocation_state.get("entity_type") or None


def session_tags(tool_context: ToolContext) -> set[str]:
    """Challenge tags from the confirmed playback (#13). Set by the engine, never by the model."""
    return set(tool_context.invocation_state.get("tags") or ())
