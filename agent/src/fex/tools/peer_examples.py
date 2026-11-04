"""Peer-example tool (issue #16): what other producers funded for a similar challenge.

Follows the data tool contract (#17, fex.tools._contract) and docs/specs/16-peer-example-tool.md: the
confirmed tags, profile crops and entity type (with any correction) come from the conversation state,
never from the model. Matching and ranking are fx_data.peers.PeerProjects.find.
"""
from functools import lru_cache
from typing import Any

from fx_data.peers import PeerProjects, ProducerProfiles, crop_set
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._contract import DataTool, EvidenceItem, run_data_tool
from fex.tools._scope import session_entity_type, session_producer_id, session_tags


@lru_cache(maxsize=1)
def _tables() -> tuple[PeerProjects, ProducerProfiles]:
    return PeerProjects.load(), ProducerProfiles.load()


def _fetch(state: dict[str, Any]) -> list[EvidenceItem]:
    peers, profiles = _tables()
    producer_id = session_producer_id(state)
    profile = profiles.get(producer_id)
    if profile is None:
        return []
    entity_type = session_entity_type(state) or profile.entity_type
    return peers.find(producer_id, set(session_tags(state)), crop_set(profile.crop), entity_type)


PEER_EXAMPLES = DataTool("find_peer_examples", "peer", _fetch)


@tool(context=True)
def find_peer_examples(tool_context: ToolContext) -> list | dict:
    """Find up to 3 Premium projects OTHER producers funded for the confirmed challenge, closest to this
    producer's crop and entity type first. Never returns the session producer's own projects.

    Each item has: source (cite it exactly), kind, text, period (start year), strength ("exact" shares
    crop and entity type, "nearest" one of them, "limited" only the challenge) and data.
    Organizations are fictional. An empty list means no comparable project exists: say so.
    """
    return run_data_tool(PEER_EXAMPLES, tool_context.invocation_state)
