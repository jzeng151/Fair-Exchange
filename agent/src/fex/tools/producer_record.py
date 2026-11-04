"""Producer-record tool (issue #14): this producer's own certification scope, Premium projects and survey context.

Follows the data tool contract (#17, fex.tools._contract) and docs/specs/14-producer-record-tool.md. The
items are built by fx_data.records.ProducerRecords.items.
"""
from functools import lru_cache
from typing import Any

from fx_data.records import ProducerRecords
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._contract import DataTool, EvidenceItem, run_data_tool
from fex.tools._scope import session_producer_id


@lru_cache(maxsize=1)
def _records() -> ProducerRecords:
    return ProducerRecords.load()


def _fetch(state: dict[str, Any]) -> list[EvidenceItem]:
    return _records().items(session_producer_id(state))


PRODUCER_RECORD = DataTool("get_producer_record", "producer_record", _fetch)


@tool(context=True)
def get_producer_record(tool_context: ToolContext) -> list | dict:
    """Return this producer's own record: certification scope, their Premium projects and safe survey
    summaries (farming, water and practices only).

    Each item has: source (cite it exactly), kind, text, period, strength and data. The first item is the
    certification scope; then their own Premium projects; then survey summaries. No survey items is normal:
    say so rather than guess. An empty list means there is no record on file for this producer.
    """
    return run_data_tool(PRODUCER_RECORD, tool_context.invocation_state)
