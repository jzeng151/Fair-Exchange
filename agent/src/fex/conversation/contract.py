"""Requests, actions and events between the chat API and the agent (issue #13, shared contract).

Spec: docs/specs/13-conversation-steps.md, "Requests, actions and events". JSON Schema and TypeScript
types are generated from these models (scripts/generate_types.py); never edit those by hand.
Actions never carry a producer ID or conversation ID: those come from the request context.
"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from fex.models import Claim

Step = Literal["intake", "playback", "respond", "consent", "feedback", "closed"]
ActionName = Literal["confirm_playback", "correct_playback", "reopen_playback", "retry_answer",
                     "set_consent", "set_feedback", "end"]
ConsentScope = Literal["internal", "internal_and_outward", "declined"]
FeedbackValue = Literal["yes", "somewhat", "no"]
Evidence = Literal["full", "limited"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------------------------------ actions

class NoArgs(_Strict):
    pass


class ConfirmPlayback(_Strict):
    name: Literal["confirm_playback"]
    args: NoArgs = Field(default_factory=NoArgs)


class CorrectPlaybackArgs(_Strict):
    text: str = Field(min_length=1, max_length=1000)


class CorrectPlayback(_Strict):
    name: Literal["correct_playback"]
    args: CorrectPlaybackArgs


class ReopenPlayback(_Strict):
    name: Literal["reopen_playback"]
    args: NoArgs = Field(default_factory=NoArgs)


class RetryAnswer(_Strict):
    name: Literal["retry_answer"]
    args: NoArgs = Field(default_factory=NoArgs)


class SetConsentArgs(_Strict):
    scope: ConsentScope


class SetConsent(_Strict):
    name: Literal["set_consent"]
    args: SetConsentArgs


class SetFeedbackArgs(_Strict):
    value: FeedbackValue


class SetFeedback(_Strict):
    name: Literal["set_feedback"]
    args: SetFeedbackArgs


class End(_Strict):
    name: Literal["end"]
    args: NoArgs = Field(default_factory=NoArgs)


Action = Annotated[ConfirmPlayback | CorrectPlayback | ReopenPlayback | RetryAnswer | SetConsent
                   | SetFeedback | End, Field(discriminator="name")]


# ----------------------------------------------------------------------------------------- requests

class _RequestBase(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    producer_id: str = Field(alias="producerId", min_length=1, description="Set by the chat API from the identity")
    conversation_id: str = Field(alias="conversationId", min_length=1, description="Set by the chat API")


class StartRequest(_RequestBase):
    kind: Literal["start"]


class MessageRequest(_RequestBase):
    kind: Literal["message"]
    text: str = Field(min_length=1, max_length=4000)


class ActionRequest(_RequestBase):
    kind: Literal["action"]
    action: Action


class ResumeRequest(_RequestBase):
    kind: Literal["resume"]


class AutoCloseRequest(_RequestBase):
    kind: Literal["auto_close"]
    reason: Literal["inactivity", "max_lifetime"]


Request = Annotated[StartRequest | MessageRequest | ActionRequest | ResumeRequest | AutoCloseRequest,
                    Field(discriminator="kind")]


# ------------------------------------------------------------------------------------------- events

class _EventBase(_Strict):
    seq: int = Field(ge=1, description="Increasing within one turn")


class TextEvent(_EventBase):
    type: Literal["text"]
    text: str


class ClaimEvent(_EventBase):
    type: Literal["claim"]
    section: Literal["insights", "peer_examples"]
    claim: Claim


class AnswerEvent(_EventBase):
    type: Literal["answer"]
    insights: list[Claim]
    peer_examples: list[Claim]
    evidence: Evidence


class StepEvent(_EventBase):
    type: Literal["step"]
    step: Step
    language: str


class ActionsEvent(_EventBase):
    type: Literal["actions"]
    allowed: list[ActionName]
    language: str


class RecordSavedEvent(_EventBase):
    type: Literal["record_saved"]
    status: Literal["completed", "declined"]
    consent_scope: ConsentScope | None
    version: int


class ErrorEvent(_EventBase):
    type: Literal["error"]
    code: Literal["agent_failed", "invalid_action", "closed"]
    message: str


class DoneEvent(_EventBase):
    type: Literal["done"]


Event = Annotated[TextEvent | ClaimEvent | AnswerEvent | StepEvent | ActionsEvent | RecordSavedEvent
                  | ErrorEvent | DoneEvent, Field(discriminator="type")]


# ------------------------------------------------------------------------------------------- resume

class Answer(_Strict):
    insights: list[Claim]
    peer_examples: list[Claim]
    evidence: Evidence


class SpokenEntry(_Strict):
    role: Literal["producer", "fex"]
    text: str
    at: datetime


class ActionEntry(_Strict):
    role: Literal["action"]
    name: ActionName
    args: dict
    at: datetime


HistoryEntry = Annotated[SpokenEntry | ActionEntry, Field(discriminator="role")]


class ResumeResponse(_Strict):
    step: Step
    language: str
    allowed: list[ActionName]
    answer: Answer | None
    history: list[HistoryEntry]


class ConversationContract(_Strict):
    """Container so one schema (and one TypeScript file) holds every shape the API and web use."""

    request: Request
    event: Event
    resume: ResumeResponse
