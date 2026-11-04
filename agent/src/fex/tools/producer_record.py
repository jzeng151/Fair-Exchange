"""Producer-record tool (issue #14): this producer's own certification scope, Premium projects and survey context."""
from functools import lru_cache

from fx_data.records import ProducerRecords
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import retrieval_refusal, session_producer_id


@lru_cache(maxsize=1)
def _records() -> ProducerRecords:
    return ProducerRecords.load()


@tool(context=True)
def get_producer_record(tool_context: ToolContext) -> list | dict:
    """Return this producer's own record: certification scope, their Premium projects and safe survey
    summaries (farming, water and practices only).
    Each item has: source (cite it exactly), kind, text, period, strength and data.
    No survey items is normal; say so rather than guess. An empty list means no record is on file.
    """
    if refusal := retrieval_refusal(tool_context):
        return refusal
    return _records().items(session_producer_id(tool_context))
