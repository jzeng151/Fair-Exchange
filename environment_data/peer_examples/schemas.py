"""Pydantic schemas for the peer-example tool."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# The 11 challenge tags from the Vision document's sample tag set.
CHALLENGE_TAGS = [
    "climate and weather",
    "water",
    "soil and land",
    "market and price",
    "labor and migration",
    "financial and access to capital",
    "education",
    "health",
    "infrastructure",
    "biodiversity and conservation",
    "social and community",
]


class PeerQuery(BaseModel):
    """What to match peers on. Supplied from session context + the tagged challenge."""

    challenge_tag: str = Field(..., description="One of the 11 challenge tags")
    crop: Optional[str] = Field(None, description="Product category, e.g. 'Coffee'")
    entity_type: Optional[str] = Field(
        None, description="Producer structure, e.g. '1st Grade', 'Estate', 'Independent Smallholder'"
    )
    exclude_account_sk: Optional[str] = Field(
        None,
        description="The session producer's account id; excluded so a producer never sees their own project back",
    )
    limit: int = Field(3, ge=1, le=10, description="Max peer examples to return")


class ProjectCitation(BaseModel):
    """Source reference for a peer example (the synthetic Premium project record)."""

    source: str = Field("FTUSA Premium Projects (synthetic)", description="Dataset name")
    project_ref: str = Field(..., description="Stable fictional project reference id")
    org_ref: str = Field(..., description="Fictionalized producer organization reference")
    detail: str = Field(..., description="Country/region/crop/subcategory the record came from")


class PeerExample(BaseModel):
    """One comparable project: what a peer did and the outcome they sought."""

    challenge: str = Field(..., description="The challenge the peer was responding to (their words, summarized)")
    action: str = Field(..., description="What the peer did (the project)")
    intended_outcome: str = Field(..., description="The outcome they were aiming for")
    crop: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    entity_type: Optional[str] = None
    match_score: float = Field(..., description="How closely this peer matches the query (0-1)")
    citation: ProjectCitation


class PeerExampleResult(BaseModel):
    """The tool's return payload: matched peer examples for the query."""

    matched: bool = Field(..., description="True if at least one comparable peer was found")
    query: PeerQuery
    examples: List[PeerExample] = Field(default_factory=list)
    note: Optional[str] = Field(
        None, description="Human-readable note, e.g. when no comparable peer exists"
    )
