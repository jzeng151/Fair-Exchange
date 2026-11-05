"""Eval evidence: what the data tools returned and what the producer was shown (#34's shared contract).

The #36 evaluators score a conversation from its saved record and this object, never from trace content.
Captured only by an engine given an evidence store, which only eval stacks (`evalAccess=true`, #5) have;
the main stack never captures it. One object per conversation, rewritten at the end of each respond step
and at close.
"""
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from fex.models import Claim
from fex.tools._contract import EvidenceItem
from fex.verifier import ReasonCode


class ShownClaim(BaseModel):
    section: Literal["insights", "peer_examples"]
    claim: Claim


class AnswerEvidence(BaseModel):
    """One respond step: an answer the producer was shown, in full or in part."""

    started_at: datetime
    tool_results: list[EvidenceItem] = Field(default_factory=list,
                                             description="Every item the data tools returned, as returned")
    claims: list[ShownClaim] = Field(default_factory=list, description="Claims emitted to the producer, in order")
    dropped: list[ReasonCode] = Field(default_factory=list,
                                      description="Reason codes of claims dropped after the last retry")
    failed: bool = Field(default=False, description="The answer failed before it finished (#13 retry_answer)")


class EvalEvidence(BaseModel):
    conversation_id: str
    producer_id: str
    # A plain string: importing the Step type would load fex.conversation, which imports this module
    final_step: str = Field(description="The #13 step the conversation was in at the last write")
    written_at: datetime
    answers: list[AnswerEvidence] = Field(default_factory=list, description="Every respond step, oldest first")

    def item_for(self, source: str) -> EvidenceItem | None:
        """The latest tool result with this source label, or None."""
        return next((item for answer in reversed(self.answers) for item in answer.tool_results
                     if item["source"] == source), None)


class EvidenceStore(Protocol):
    def get(self, conversation_id: str) -> EvalEvidence | None: ...

    def put(self, evidence: EvalEvidence) -> None: ...


class InMemoryEvidenceStore:
    """For offline eval runs and tests. Round-trips through JSON, as a bucket would."""

    def __init__(self) -> None:
        self._objects: dict[str, str] = {}

    def get(self, conversation_id: str) -> EvalEvidence | None:
        raw = self._objects.get(conversation_id)
        return EvalEvidence.model_validate_json(raw) if raw is not None else None

    def put(self, evidence: EvalEvidence) -> None:
        self._objects[evidence.conversation_id] = evidence.model_dump_json()
