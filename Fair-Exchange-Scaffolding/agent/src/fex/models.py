"""Pydantic schemas: the single source of truth for records and tool I/O.
JSON Schema and TypeScript types are generated from these. Do not hand-edit generated files.
TODO(#6): finalize fields with the team and generate JSON Schema + TS types.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

CHALLENGE_TAGS = [
    "climate and weather", "water", "soil and land", "market and price", "labor and migration",
    "financial and access to capital", "education", "health", "infrastructure",
    "biodiversity and conservation", "social and community",
]


class EvidenceStrength(str, Enum):
    exact = "exact"        # exact region match
    nearest = "nearest"    # nearest available data
    limited = "limited"    # limited evidence


class Citation(BaseModel):
    """Every claim must carry one; a claim without source + clause is rejected."""
    source: str = Field(min_length=1, description="Dataset, record or document the fact came from")
    standard_clause: str = Field(min_length=1, description="Related APS/FPS clause, e.g. 'APS 3.2.1'")
    period: str | None = None
    strength: EvidenceStrength = EvidenceStrength.exact


class Claim(BaseModel):
    text: str
    citation: Citation


class ReviewStatus(str, Enum):
    pending = "pending"
    reviewed = "reviewed"
    not_applicable = "n/a"   # declined records


class ConversationRecord(BaseModel):
    """One record per completed or declined conversation."""
    record_id: str
    producer_id: str
    status: str = Field(pattern="^(completed|declined)$")
    consent: str = Field(pattern="^(granted|declined)$")
    source: str = "agent conversation"
    created_at: datetime
    # Narrative fields: only when consent is granted
    language: str | None = None
    entity_type: str | None = None
    summary_original: str | None = None
    summary_english: str | None = None
    tags: list[str] = []
    insights: list[Claim] = []
    peer_examples: list[Claim] = []
    feedback: str | None = None
    pii_flag: bool = False
    review_status: ReviewStatus = ReviewStatus.pending
