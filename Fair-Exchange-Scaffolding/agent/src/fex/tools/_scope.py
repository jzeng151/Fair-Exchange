"""Shared scope helper: the ONLY way a tool learns who the producer is."""
from strands.types.tools import ToolContext


def session_producer_id(tool_context: ToolContext) -> str:
    producer_id = tool_context.invocation_state.get("producer_id")
    if not producer_id:
        raise PermissionError("No producer in session")
    return producer_id
