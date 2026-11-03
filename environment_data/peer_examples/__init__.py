"""Peer-example tool for the Producer Exchange Agent.

Answers the second half of the agent's promise: "what others are doing." Given a
producer's challenge (as a challenge tag), crop, and entity type, it finds
comparable Premium projects other producers funded in response to similar
challenges and reports what they did and what outcome they were after, each with
a citation.

Spec-aligned shape (mirrors regional_context/):
  - prepare.py builds a static, tagged peer-projects table from the synthetic
    Premium projects CSV once (no runtime file parsing of the raw CSV).
  - tool.py reads only that static table and matches on (challenge_tag, crop,
    entity_type), excluding the session producer's own account (scope rule).
  - Pydantic schemas carry per-claim citations.
"""

from .schemas import (
    PeerExample,
    PeerExampleResult,
    PeerQuery,
    ProjectCitation,
)

__all__ = [
    "PeerQuery",
    "ProjectCitation",
    "PeerExample",
    "PeerExampleResult",
]
