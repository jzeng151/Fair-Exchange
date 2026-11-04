"""Peer-example tool (issue #16): what other producers funded for a similar challenge."""
from functools import lru_cache

from fx_data.peers import PeerProjects, ProducerProfiles
from strands import tool
from strands.types.tools import ToolContext

from fex.models import ChallengeTag
from fex.tools._scope import session_producer_id

MAX_EXAMPLES = 3


@lru_cache(maxsize=1)
def _tables() -> tuple[PeerProjects, ProducerProfiles]:
    return PeerProjects.load(), ProducerProfiles.load()


@tool(context=True)
def find_peer_examples(challenge: ChallengeTag, tool_context: ToolContext) -> list:
    """Find Premium projects OTHER producers funded for the same challenge, closest to this
    producer's crop and entity type first. Never returns the session producer's own records.

    Args:
        challenge: The challenge tag for what the producer described.

    Each result has: source (cite it), challenge, action, intended_outcome, status (Completed,
    In Progress or In Planning; null when the sample cannot tell which of several similar projects it is), crop, entity_type, country, region and match_score.
    Organizations are fictionalized. An empty list means no comparable project exists: say so.
    """
    producer_id = session_producer_id(tool_context)
    peers, profiles = _tables()
    profile = profiles.get(producer_id)
    if profile is None:
        return []
    return peers.find(challenge, profile, limit=MAX_EXAMPLES)
