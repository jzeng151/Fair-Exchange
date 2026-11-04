"""Regional-context tool (issue #15): what the open data shows for this producer's region, crop and challenge.

Follows the data tool contract (#17, fex.tools._contract) and docs/specs/15-regional-context-tool.md:
location and crops from the profile, tags from the confirmed playback, rows from the #8 fact table.
"""
from functools import lru_cache
from typing import Any

from fx_data.peers import ProducerProfiles
from fx_data.regional import RegionalFacts, normalize_crops
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._contract import DataTool, EvidenceItem, run_data_tool
from fex.tools._scope import session_producer_id, session_tags


@lru_cache(maxsize=1)
def _tables() -> tuple[RegionalFacts, ProducerProfiles]:
    return RegionalFacts.load(), ProducerProfiles.load()


def _fetch(state: dict[str, Any]) -> list[EvidenceItem]:
    facts, profiles = _tables()
    profile = profiles.get(session_producer_id(state))
    if profile is None:
        return []
    return facts.lookup(profile.country, profile.region, normalize_crops(profile.crop), set(session_tags(state)))


REGIONAL_CONTEXT = DataTool("get_regional_context", "regional", _fetch)


@tool(context=True)
def get_regional_context(tool_context: ToolContext) -> list | dict:
    """Return regional open data (rainfall, water stress, prices) for this producer's region, crop and
    confirmed challenge.

    Location, crop and challenge come from the session, never from the conversation.
    Each item has: source (cite it exactly), kind, text, period, strength ("exact" is this region,
    "nearest" is the country average, "limited" is a world benchmark, not a local price) and data.
    An empty list means there is no data for this producer: say so, do not guess.
    """
    return run_data_tool(REGIONAL_CONTEXT, tool_context.invocation_state)
