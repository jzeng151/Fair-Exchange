"""FEX data tools. Contract (#17): fex.tools._contract. Every tool reads the producer and the confirmed
conversation from tool_context.invocation_state and takes no model-settable arguments at all."""
from fex.tools._contract import DataTool
from fex.tools.peer_examples import PEER_EXAMPLES, find_peer_examples
from fex.tools.producer_record import PRODUCER_RECORD, get_producer_record
from fex.tools.regional_context import REGIONAL_CONTEXT, get_regional_context
from fex.tools.standards import STANDARDS, find_standards

ALL_TOOLS = [get_producer_record, get_regional_context, find_peer_examples, find_standards]
# Contract entry for each Strands tool, so the engine can backstop a call the model skipped
DATA_TOOLS: dict[str, DataTool] = {t.name: t for t in (PRODUCER_RECORD, REGIONAL_CONTEXT, PEER_EXAMPLES, STANDARDS)}
