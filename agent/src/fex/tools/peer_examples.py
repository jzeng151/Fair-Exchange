"""Peer-example tool (issue #16): what other producers funded for a similar challenge.

Follows the data tool contract (#17, fex.tools._contract): the confirmed tags come from the conversation
state, never from the model. Ranking and source labels are still the merged #54 behavior; aligning them
with docs/specs/16-peer-example-tool.md is the #16 retro.
"""
from dataclasses import replace
from functools import lru_cache
from typing import Any

from fx_data.peers import PeerProjects, ProducerProfile, ProducerProfiles, _crops
from fx_data.text import normalize
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._contract import DataTool, EvidenceItem, run_data_tool
from fex.tools._scope import session_entity_type, session_producer_id, session_tags

MAX_EXAMPLES = 3


@lru_cache(maxsize=1)
def _tables() -> tuple[PeerProjects, ProducerProfiles]:
    return PeerProjects.load(), ProducerProfiles.load()


def _strength(row: dict, profile: ProducerProfile) -> str:
    """Tag plus crop and entity type: exact; tag plus one of them: nearest; tag only: limited (#16)."""
    crop = bool(_crops(row["crop"]) & _crops(profile.crop))
    entity = bool(profile.entity_type) and normalize(row["entity_type"]) == normalize(profile.entity_type)
    return "exact" if crop and entity else "nearest" if crop or entity else "limited"


def _item(row: dict, profile: ProducerProfile) -> EvidenceItem:
    period = " to ".join(d for d in (row.get("start_date"), row.get("end_date")) if d) or None
    return EvidenceItem(source=row["source"], kind="peer",
                        text=f"{row['name']} ({', '.join(x for x in (row.get('status'), row.get('country')) if x)}): "
                             f"{row['action']}",
                        period=period, strength=_strength(row, profile),
                        data={k: v for k, v in row.items() if k != "source"})


def _fetch(state: dict[str, Any]) -> list[EvidenceItem]:
    peers, profiles = _tables()
    profile = profiles.get(session_producer_id(state))
    if profile is None:
        return []
    if corrected := session_entity_type(state):
        profile = replace(profile, entity_type=corrected)
    rows, seen = [], set()
    for tag in session_tags(state):
        for row in peers.find(tag, profile, limit=MAX_EXAMPLES):
            if row["project_ref"] not in seen and row["org_ref"] not in seen:
                seen |= {row["project_ref"], row["org_ref"]}
                rows.append(row)
    rows.sort(key=lambda r: -r["match_score"])  # stable: ties keep the confirmed tag order
    return [_item(r, profile) for r in rows[:MAX_EXAMPLES]]


PEER_EXAMPLES = DataTool("find_peer_examples", "peer", _fetch)


@tool(context=True)
def find_peer_examples(tool_context: ToolContext) -> list | dict:
    """Find Premium projects OTHER producers funded for the confirmed challenge, closest to this
    producer's crop and entity type first. Never returns the session producer's own records.

    Each item has: source (cite it exactly), kind, text, period, strength and data (challenge, action,
    intended_outcome, status, crop, entity_type, country, region, match_score).
    Organizations are fictionalized. An empty list means no comparable project exists: say so.
    """
    return run_data_tool(PEER_EXAMPLES, tool_context.invocation_state)
