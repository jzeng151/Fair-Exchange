"""Producer-record tool (issue #14): this producer's own profile, Premium projects and survey context."""
from functools import lru_cache

from fx_data.records import ProducerRecords
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import session_producer_id


@lru_cache(maxsize=1)
def _records() -> ProducerRecords:
    return ProducerRecords.load()


@tool(context=True)
def get_producer_record(tool_context: ToolContext) -> dict:
    """Return this producer's own profile, Premium projects and safe survey fields (farming, water, practices only).

    Returns `found`, then:
      - profile: country, region, crop, entity_type, certification_status, certification_scope, source
      - premium_projects: their own projects (name, challenge, action, intended_outcome, status, dates, source)
      - survey: respondents, facts (each with text, source, period, respondents), and a note when
        there is nothing to summarize. No survey data is normal; say so rather than guess.
    Cite each item's `source`.
    """
    producer_id = session_producer_id(tool_context)
    record = _records().get(producer_id)
    if record is None:
        return {"found": False, "note": "No record on file for this producer."}
    return {"found": True, **record}
