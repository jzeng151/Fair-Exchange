"""Conversation record schema: the single source of truth (issue #6).

JSON Schema and TypeScript types are generated from these models. Do not hand-edit generated files.
"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

# The 11 challenge tags from the Vision document
ChallengeTag = Literal[
    "climate and weather", "water", "soil and land", "market and price", "labor and migration",
    "financial and access to capital", "education", "health", "infrastructure",
    "biodiversity and conservation", "social and community",
]


class Citation(BaseModel):
    """Where a claim comes from. Every insight and peer example must carry one."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, description="Dataset, record or document the fact came from")
    standard_clause: str = Field(min_length=1, description="Related APS/FPS clause, e.g. 'APS 3.2.1'")
    period: str | None = Field(default=None, description="Time period of the data, if any")
    strength: Literal["exact", "nearest", "limited"] = Field(
        default="exact", description="How well the evidence matches this producer's area")


class Claim(BaseModel):
    """One insight or peer example given to the producer, with its citation."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    citation: Citation


class StoredConsent(BaseModel):
    """The producer agreed to store the conversation. Consent is a scope, not a yes/no:

    internal: stored for Fair Trade USA's own review and trends
    internal_and_outward: may also be shared outward (e.g. aggregated for partners)
    """

    model_config = ConfigDict(extra="forbid")

    scope: Literal["internal", "internal_and_outward"]
    recorded_at: datetime


class DeclinedConsent(BaseModel):
    """The producer declined: nothing narrative is stored."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["declined"]
    recorded_at: datetime


class _RecordBase(BaseModel):
    """Fields every record has. Unknown fields are rejected, so nothing slips in unnoticed."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1, description="Set from the session, never from the conversation")
    created_at: datetime
    source: Literal["agent conversation"] = Field(
        default="agent conversation", description="Never confused with mandatory or compliance reporting data")


# Cross-field rule the JSON Schema must carry too (TypeScript cannot express it)
_NON_ENGLISH_NEEDS_ENGLISH_SUMMARY = {
    "if": {"required": ["language"], "properties": {"language": {"not": {"const": "en"}}}},
    "then": {"required": ["summary_english"],
             "properties": {"summary_english": {"type": "string", "minLength": 1}}},
}


class CompletedRecord(_RecordBase):
    """A conversation the producer agreed to save."""

    model_config = ConfigDict(json_schema_extra=_NON_ENGLISH_NEEDS_ENGLISH_SUMMARY)

    status: Literal["completed"]
    consent: StoredConsent
    language: str = Field(pattern=r"^[a-z]{2}$", description="ISO 639-1 code of the producer's language, e.g. 'es'")
    entity_type: str = Field(min_length=1, description="e.g. cooperative, smallholder, hired-labor farm, processor")
    summary_original: str = Field(min_length=1, description="The challenge in the producer's own words and language")
    summary_english: str | None = Field(default=None, min_length=1,
                                       description="English version; required for non-English conversations")
    tags: list[ChallengeTag] = Field(min_length=1, description="Challenge tags from the 11-tag set")
    insights: list[Claim] = Field(default_factory=list, description="What the data shows, as given to the producer")
    peer_examples: list[Claim] = Field(default_factory=list, description="What others tried, as given to the producer")
    feedback: Literal["yes", "somewhat", "no"] | None = Field(default=None, description="Was the guidance helpful?")
    pii_flag: bool = Field(default=False, description="Personal information flagged for human review; never redacted")
    review_status: Literal["pending", "reviewed"] = "pending"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def _non_english_needs_english_summary(self):
        if self.language != "en" and not self.summary_english:
            raise ValueError("non-English records are stored in the producer's language and in English")
        return self


class DeclinedRecord(_RecordBase):
    """The producer declined. Only identifiers, status and time are kept: no narrative content."""

    status: Literal["declined"]
    consent: DeclinedConsent


ConversationRecord = Annotated[CompletedRecord | DeclinedRecord, Field(discriminator="status")]
_record_adapter = TypeAdapter(ConversationRecord)


def parse_record(data: dict) -> CompletedRecord | DeclinedRecord:
    """Validate a stored or incoming record, choosing the type from its `status`."""
    return _record_adapter.validate_python(data)
