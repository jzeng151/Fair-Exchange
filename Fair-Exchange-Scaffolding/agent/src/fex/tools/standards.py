from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import session_producer_id


@tool(context=True)
def check_standards(claim: str, tool_context: ToolContext) -> dict:
    """Return the APS/FPS clauses related to a claim, so every claim can cite one."""
    producer_id = session_producer_id(tool_context)
    # TODO(#17): implement
    raise NotImplementedError(f"check_standards not implemented yet (producer {producer_id[:6]}…)")
