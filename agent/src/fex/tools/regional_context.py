"""Regional-context tool (issue #15): what the open data shows for this producer's region and crop.

Follows the data tool contract (#17, fex.tools._contract). Matching and source labels are still the
merged #53 behavior; aligning them with docs/specs/15-regional-context-tool.md is the #15 retro.
"""
from functools import lru_cache
from typing import Any

from fx_data.peers import ProducerProfiles
from fx_data.regional import RegionalFacts
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._contract import DataTool, EvidenceItem, run_data_tool
from fex.tools._scope import session_producer_id

_DATA_FIELDS = ("metric", "value", "unit")


@lru_cache(maxsize=1)
def _tables() -> tuple[RegionalFacts, ProducerProfiles]:
    return RegionalFacts.load(), ProducerProfiles.load()


def _fetch(state: dict[str, Any]) -> list[EvidenceItem]:
    facts, profiles = _tables()
    profile = profiles.get(session_producer_id(state))
    if profile is None or not profile.country:
        return []
    answer = facts.lookup(profile.country, profile.region, profile.crop).as_dict()
    if not answer["matched"]:
        return []
    region = {"country": profile.country, "region": profile.region, "crop": profile.crop}
    return [EvidenceItem(source=f["source"], kind="regional", text=f["text"], period=f.get("period"),
                         strength=f["strength"],
                         data={**{k: f[k] for k in _DATA_FIELDS if k in f},
                               "match_level": answer["match_level"], "region": region})
            for f in answer["facts"]]


REGIONAL_CONTEXT = DataTool("get_regional_context", "regional", _fetch)


@tool(context=True)
def get_regional_context(tool_context: ToolContext) -> list | dict:
    """Return regional open data (rainfall, water stress, prices) for this producer's location and crop.

    The location and crop come from the session producer's record, never from the conversation.
    Each item has: source (cite it exactly), kind, text, period, strength ("nearest" means it describes a
    point near the region's centre; "limited" means a world benchmark, not a local price) and data.
    An empty list means there is no data for this producer's region: say so, do not guess.
    """
    return run_data_tool(REGIONAL_CONTEXT, tool_context.invocation_state)
