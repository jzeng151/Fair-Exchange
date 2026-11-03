from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import session_producer_id


@tool(context=True)
def get_producer_record(tool_context: ToolContext) -> dict:
    """Return this producer's own profile, Premium projects and safe survey fields (farming, water, practices only)."""
    producer_id = session_producer_id(tool_context)
    # TODO(#14): implement
    raise NotImplementedError(f"get_producer_record not implemented yet (producer {producer_id[:6]}…)")
