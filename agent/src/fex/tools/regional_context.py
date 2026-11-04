"""Regional-context tool (issue #15): what the open data shows for this producer's region and crop."""
from functools import lru_cache

from fx_data.peers import ProducerProfiles
from fx_data.regional import RegionalFacts
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import retrieval_refusal, session_producer_id


@lru_cache(maxsize=1)
def _tables() -> tuple[RegionalFacts, ProducerProfiles]:
    return RegionalFacts.load(), ProducerProfiles.load()


@tool(context=True)
def get_regional_context(tool_context: ToolContext) -> dict:
    """Return regional open data (rainfall, water stress, prices) for this producer's location and crop.

    The location and crop come from the session producer's record, never from the conversation.
    Each fact has: text, source (cite it), period, and strength ("nearest" means it describes a
    point near the region's centre; "limited" means a world benchmark, not a local price).
    If `matched` is false, there is no data for this producer's region: say so, do not guess.
    """
    if refusal := retrieval_refusal(tool_context):
        return refusal
    producer_id = session_producer_id(tool_context)
    facts, profiles = _tables()
    profile = profiles.get(producer_id)
    if profile is None or not profile.country:
        return {"matched": False, "match_level": "none", "facts": [],
                "note": "This producer's location is not on record."}
    answer = facts.lookup(profile.country, profile.region, profile.crop).as_dict()
    answer["region"] = {"country": profile.country, "region": profile.region, "crop": profile.crop}
    return answer
