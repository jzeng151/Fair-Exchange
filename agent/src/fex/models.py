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


class ConsentChoice(BaseModel):
    """One consent choice the producer made (#19, #26). Non-narrative, so allowed on declined records."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["internal", "internal_and_outward", "declined"]
    recorded_at: datetime


class ModelUsage(BaseModel):
    """Tokens one model used in this conversation, for the AI footprint (#26, #29). Non-narrative."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class EarlierAnswer(BaseModel):
    """An answer shown to the producer and later replaced (#26).

    reopened: the full answer shown before the producer reopened the playback
    interrupted: only the claims shown before a failed answer was retried
    """

    model_config = ConfigDict(extra="forbid")

    given_at: datetime
    reason: Literal["reopened", "interrupted"]
    insights: list[Claim] = Field(default_factory=list)
    peer_examples: list[Claim] = Field(default_factory=list)
    evidence: Literal["full", "limited"] | None = Field(
        default=None, description="null for an interrupted answer, which never finished")


class _RecordBase(BaseModel):
    """Fields every record has. Unknown fields are rejected, so nothing slips in unnoticed."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1, description="Set from the session, never from the conversation")
    created_at: datetime
    source: Literal["agent conversation"] = Field(
        default="agent conversation", description="Never confused with mandatory or compliance reporting data")
    # Write-back (#26): one record per conversation, saved with a version and owner check
    updated_at: datetime = Field(description="Time of the latest save")
    version: int = Field(ge=1, description="Starts at 1; incremented on every save; used for conditional writes")
    closed_at: datetime | None = Field(
        default=None, description="Set when the conversation closes. Records are reviewable only when set.")
    consent_history: list[ConsentChoice] = Field(
        default_factory=list, description="The producer's distinct consent choices, in order")
    ai_usage: list[ModelUsage] = Field(
        default_factory=list, description="Tokens per model for this conversation (AI footprint)")


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
    tags: list[ChallengeTag] = Field(min_length=1, description="Challenge tags from the 11-tag set (the agent's)")
    evidence: Literal["full", "limited"] = Field(
        description="limited when the shown answer had no insights or no peer examples")
    earlier_answers: list[EarlierAnswer] = Field(
        default_factory=list, description="Answers shown and later replaced, oldest first")
    insights: list[Claim] = Field(default_factory=list, description="What the data shows, as given to the producer")
    peer_examples: list[Claim] = Field(default_factory=list, description="What others tried, as given to the producer")
    feedback: Literal["yes", "somewhat", "no"] | None = Field(default=None, description="Was the guidance helpful?")
    pii_flag: bool = Field(default=False, description="Personal information flagged for human review; never redacted")
    review_status: Literal["pending", "reviewed"] = "pending"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    # Reviewer corrections sit next to the agent's values; they never overwrite them (#26)
    reviewer_tags: list[ChallengeTag] | None = Field(default=None, description="Reviewer's corrected tags")
    reviewer_summary_original: str | None = Field(
        default=None, min_length=1, description="Reviewer's corrected summary in the producer's language")
    reviewer_summary_english: str | None = Field(
        default=None, min_length=1, description="Reviewer's corrected English summary")

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
