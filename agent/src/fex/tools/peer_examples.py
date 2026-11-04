"""Peer-example tool (issue #16): what other producers funded for a similar challenge."""
from functools import lru_cache

from fx_data.peers import PeerProjects, ProducerProfiles, crop_set
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._scope import retrieval_refusal, session_entity_type, session_producer_id, session_tags


@lru_cache(maxsize=1)
def _tables() -> tuple[PeerProjects, ProducerProfiles]:
    return PeerProjects.load(), ProducerProfiles.load()


@tool(context=True)
def find_peer_examples(tool_context: ToolContext) -> list | dict:
    """Find up to 3 Premium projects OTHER producers funded for the confirmed challenge, closest to this
    producer's crop and entity type first. Never returns the session producer's own projects.
    Each item has: source (cite it exactly), kind, text, period (start year), strength ("exact" shares
    crop and entity type, "nearest" one of them, "limited" only the challenge) and data.
    Organizations are fictional. An empty list means no comparable project exists: say so.
    """
    if refusal := retrieval_refusal(tool_context):
        return refusal
    producer_id = session_producer_id(tool_context)
    peers, profiles = _tables()
    profile = profiles.get(producer_id)
    if profile is None:
        return []
    entity_type = session_entity_type(tool_context) or profile.entity_type
    return peers.find(producer_id, session_tags(tool_context), crop_set(profile.crop), entity_type)
