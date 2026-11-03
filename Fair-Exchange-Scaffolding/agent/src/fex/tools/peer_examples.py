from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import session_producer_id


@tool(context=True)
def find_peer_examples(challenge: str, tool_context: ToolContext) -> list:
    """Find Premium projects OTHER producers with a similar crop and entity type funded for a
    similar challenge. Never returns the session producer's own records."""
    producer_id = session_producer_id(tool_context)
    # TODO(#16): Knowledge Base retrieval over Premium projects (multilingual embeddings)
    raise NotImplementedError(f"find_peer_examples not implemented yet (producer {producer_id[:6]}…)")
