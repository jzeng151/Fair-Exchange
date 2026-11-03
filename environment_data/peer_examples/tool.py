"""Runtime peer-example tool (Strands @tool).

Given the session producer's challenge tag, crop, and entity type, find
comparable Premium projects other producers funded, and report what they did and
the outcome they sought, each with a citation.

Scope enforcement: the session producer's own account id is passed as
`exclude_account_sk` and filtered out, so a producer can never be shown their own
project as a "peer". Matching uses only the tag/crop/entity passed from session
context; the tool reads a static pre-extracted table and makes no network calls.

Strands is optional at import time (same pattern as the climate tool): real @tool
if the SDK is installed, otherwise the plain function for testing.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import List, Optional

from .schemas import (
    PeerExample,
    PeerExampleResult,
    PeerQuery,
    ProjectCitation,
)

_DEFAULT_TABLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "peer_projects.json",
)

# Relative weights for the match score (sum to 1.0).
_W_TAG = 0.5
_W_CROP = 0.3
_W_ENTITY = 0.2


@lru_cache(maxsize=1)
def _load_table(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _norm(v: Optional[str]) -> Optional[str]:
    return v.strip().lower() if v else None


def _crop_matches(query_crop: Optional[str], project_crop: Optional[str]) -> bool:
    """Crop match, tolerant of multi-crop fields like 'Cocoa;Coffee'."""
    if not query_crop or not project_crop:
        return False
    q = _norm(query_crop)
    parts = [p.strip().lower() for p in project_crop.split(";")]
    return q in parts


def _score(query: PeerQuery, project: dict) -> float:
    """Closeness of a project to the query. Tag is required (filtered before)."""
    score = _W_TAG  # tag already matched to reach here
    if _crop_matches(query.crop, project.get("crop")):
        score += _W_CROP
    if query.entity_type and _norm(query.entity_type) == _norm(project.get("entity_type")):
        score += _W_ENTITY
    return round(score, 3)


def get_peer_examples(
    challenge_tag: str,
    crop: Optional[str] = None,
    entity_type: Optional[str] = None,
    exclude_account_sk: Optional[str] = None,
    limit: int = 3,
    table_path: Optional[str] = None,
) -> PeerExampleResult:
    """Return comparable peer Premium projects for a producer's challenge.

    Args:
        challenge_tag: One of the 11 challenge tags (from the agent's tagging).
        crop: Product category from session context.
        entity_type: Producer structure from session context.
        exclude_account_sk: The session producer's account id, excluded from results.
        limit: Max examples to return (1-10).

    Returns:
        PeerExampleResult with peer examples (what they did, intended outcome) and
        citations. If no comparable peer exists, `matched` is False with a note,
        so the agent can say it found no precedent rather than inventing one.
    """
    query = PeerQuery(
        challenge_tag=challenge_tag,
        crop=crop,
        entity_type=entity_type,
        exclude_account_sk=exclude_account_sk,
        limit=limit,
    )
    path = table_path or os.getenv("PEER_PROJECTS_TABLE", _DEFAULT_TABLE)

    try:
        table = _load_table(path)
    except FileNotFoundError:
        return PeerExampleResult(
            matched=False,
            query=query,
            note="No pre-extracted peer table found. Run `python -m peer_examples.prepare`.",
        )

    tag = _norm(challenge_tag)
    candidates = [
        p
        for p in table.get("projects", [])
        if _norm(p.get("challenge_tag")) == tag
        and p.get("_account_sk") != exclude_account_sk
    ]

    if not candidates:
        return PeerExampleResult(
            matched=False,
            query=query,
            note=f"No peer projects found for challenge '{challenge_tag}'.",
        )

    ranked = sorted(candidates, key=lambda p: _score(query, p), reverse=True)

    examples: List[PeerExample] = []
    for p in ranked[: query.limit]:
        loc = ", ".join(x for x in (p.get("region"), p.get("country")) if x)
        examples.append(
            PeerExample(
                challenge=p.get("challenge") or "(not recorded)",
                action=p.get("action") or p.get("name") or "(not recorded)",
                intended_outcome=p.get("intended_outcome") or "(not recorded)",
                crop=p.get("crop"),
                country=p.get("country"),
                region=p.get("region"),
                entity_type=p.get("entity_type"),
                match_score=_score(query, p),
                citation=ProjectCitation(
                    project_ref=p.get("project_ref", "PROJ-UNKNOWN"),
                    org_ref=p.get("org_ref", "ORG-UNKNOWN"),
                    detail=(
                        f"{loc or 'location n/a'}; crop {p.get('crop') or 'n/a'}; "
                        f"{p.get('subcategory') or 'environmental'}"
                    ),
                ),
            )
        )

    return PeerExampleResult(matched=True, query=query, examples=examples)


# --- Strands tool registration (optional import) ---------------------------
try:
    from strands import tool  # type: ignore

    @tool
    def peer_examples_tool(
        challenge_tag: str,
        crop: Optional[str] = None,
        entity_type: Optional[str] = None,
        exclude_account_sk: Optional[str] = None,
        limit: int = 3,
    ) -> dict:
        """Find comparable Premium projects other producers funded for a similar
        challenge, and report what they did and the outcome they sought, with
        citations. challenge_tag/crop/entity_type/exclude_account_sk come from
        session context. Says so when no comparable peer exists.
        """
        return get_peer_examples(
            challenge_tag, crop, entity_type, exclude_account_sk, limit
        ).model_dump()

except ImportError:
    peer_examples_tool = get_peer_examples  # type: ignore
