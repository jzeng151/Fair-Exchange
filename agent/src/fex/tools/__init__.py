"""FEX tools. Scope rule: every tool reads producer_id from tool_context.invocation_state.
Never add producer_id or location as a tool parameter."""
from fex.tools.peer_examples import find_peer_examples
from fex.tools.regional_context import get_regional_context

ALL_TOOLS = [get_regional_context, find_peer_examples]
