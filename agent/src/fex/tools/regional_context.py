"""Regional-context tool (issue #15): what the open data shows for this producer's region, crop and challenge."""
from functools import lru_cache

from fx_data.peers import ProducerProfiles
from fx_data.regional import RegionalFacts, normalize_crops
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import retrieval_refusal, session_producer_id, session_tags


@lru_cache(maxsize=1)
def _tables() -> tuple[RegionalFacts, ProducerProfiles]:
    return RegionalFacts.load(), ProducerProfiles.load()


@tool(context=True)
def get_regional_context(tool_context: ToolContext) -> list | dict:
    """Return regional open data (rainfall, water stress, prices) for this producer's region, crop and
    confirmed challenge. Location, crop and challenge come from the session, never from the conversation.
    Each item has: source (cite it exactly), kind, text, period, strength ("exact" is this region,
    "nearest" is the country average, "limited" is a world benchmark, not a local price) and data.
    An empty list means there is no data for this producer: say so, do not guess.
    """
    if refusal := retrieval_refusal(tool_context):
        return refusal
    producer_id = session_producer_id(tool_context)
    facts, profiles = _tables()
    profile = profiles.get(producer_id)
    if profile is None:
        return []
    return facts.lookup(profile.country, profile.region, normalize_crops(profile.crop), session_tags(tool_context))
