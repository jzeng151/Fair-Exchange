from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import session_producer_id


@tool(context=True)
def get_regional_context(tool_context: ToolContext) -> dict:
    """Return regional open data (rainfall, water stress, prices) for this producer's location and crop."""
    producer_id = session_producer_id(tool_context)
    # TODO(#15): implement
    raise NotImplementedError(f"get_regional_context not implemented yet (producer {producer_id[:6]}…)")
