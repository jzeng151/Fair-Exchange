"""Bedrock Guardrail in detect mode on every FEX model call (issue #12, docs/specs/12-guardrail.md).

The Guardrail is defined in CDK (infra/lib/guardrail.ts) with every policy action set to NONE, so it
flags and never blocks. This module:

- builds the BedrockModel settings that attach it, with redaction explicitly off, so nothing the
  producer wrote or FEX answered is altered even if a policy action is changed later;
- logs each detected policy to CloudWatch with the conversation ID, policy type and topic or
  category only. Never text: the trace's `modelOutput` and any `match` fields are not read.

Findings change no behavior and are never written to the record (#21, #26).
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from strands.models.bedrock import BedrockModel

log = logging.getLogger(__name__)

ENV_ID = "FEX_GUARDRAIL_ID"
ENV_VERSION = "FEX_GUARDRAIL_VERSION"

#: Key the engine sets in `invocation_state` so each model call knows its conversation.
CONVERSATION_KEY = "conversation_id"


def guardrail_settings() -> dict[str, Any]:
    """BedrockModel keyword arguments that attach the Guardrail, or {} when it is not configured."""
    guardrail_id, version = os.environ.get(ENV_ID), os.environ.get(ENV_VERSION)
    if not guardrail_id or not version:
        log.warning("guardrail not configured: set %s and %s", ENV_ID, ENV_VERSION)
        return {}
    return {
        "guardrail_id": guardrail_id,
        "guardrail_version": version,
        "guardrail_trace": "enabled",
        # Strands redacts input by default when a policy blocks. Detect mode never blocks, but set both
        # off explicitly so a later policy change cannot alter the conversation (spec, "Attachment").
        "guardrail_redact_input": False,
        "guardrail_redact_output": False,
    }


# Policy key in a Guardrail assessment -> (policy type we log, list key, field holding the category).
# Fields that carry text (`match`) are never read.
_POLICIES: tuple[tuple[str, str, str, str], ...] = (
    ("topicPolicy", "topic", "topics", "name"),
    ("contentPolicy", "content", "filters", "type"),
    ("wordPolicy", "word", "managedWordLists", "type"),
    ("sensitiveInformationPolicy", "sensitive_information", "piiEntities", "type"),
    ("sensitiveInformationPolicy", "sensitive_information", "regexes", "name"),
    ("contextualGroundingPolicy", "contextual_grounding", "filters", "type"),
)


def _detected(entry: dict[str, Any]) -> bool:
    # Detect mode reports action NONE; `detected` says whether the policy matched. Older traces omit it,
    # and Bedrock only lists entries that matched, so a missing flag counts as detected.
    return entry.get("detected", True) is not False


def _from_assessment(assessment: dict[str, Any], source: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for policy_key, policy, list_key, field in _POLICIES:
        for entry in (assessment.get(policy_key) or {}).get(list_key) or []:
            if isinstance(entry, dict) and _detected(entry):
                found.append({"source": source, "policy": policy, "category": str(entry.get(field, "unknown"))})
    # Custom words carry only the matched text, so log that one matched, never what it was.
    for entry in (assessment.get("wordPolicy") or {}).get("customWords") or []:
        if isinstance(entry, dict) and _detected(entry):
            found.append({"source": source, "policy": "word", "category": "custom_word"})
    return found


def findings(trace: dict[str, Any]) -> list[dict[str, str]]:
    """Detected policies in a Guardrail trace, as {source, policy, category}. Contains no text."""
    out: list[dict[str, str]] = []
    for assessment in (trace.get("inputAssessment") or {}).values():
        out += _from_assessment(assessment, "input")
    for assessments in (trace.get("outputAssessments") or {}).values():
        for assessment in assessments or []:
            out += _from_assessment(assessment, "output")
    return out


def log_findings(chunk: dict[str, Any], conversation_id: str | None) -> None:
    """Log the Guardrail findings carried by one model stream chunk, if any."""
    trace = ((chunk.get("metadata") or {}).get("trace") or {}).get("guardrail")
    if not isinstance(trace, dict):
        return
    for finding in findings(trace):
        # WARNING so it reaches CloudWatch under the default logging level. JSON for Logs Insights.
        log.warning("guardrail_finding %s",
                    json.dumps({"event": "guardrail_finding", "conversation_id": conversation_id, **finding}))


class GuardrailFindingsMixin:
    """Mix into a Strands model to log Guardrail findings from its stream. Chunks pass through unchanged.

    This covers the Converse *input* assessment. FEX takes every model output as structured output, which
    Bedrock returns as tool-use arguments that the Converse guardrail does not assess, so generated text is
    checked separately with `assess_output` after each call.
    """

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        conversation_id = (kwargs.get("invocation_state") or {}).get(CONVERSATION_KEY)
        async for chunk in super().stream(*args, **kwargs):  # type: ignore[misc]
            if isinstance(chunk, dict) and "metadata" in chunk:
                try:
                    log_findings(chunk, conversation_id)
                except Exception:  # noqa: BLE001 - logging must never break a model call
                    log.exception("guardrail finding could not be logged for conversation %s", conversation_id)
            yield chunk


class OutputAssessor:
    """Runs a detect-only ApplyGuardrail pass over generated text and logs findings.

    Converse guardrails skip the structured-output text (toolUse.input), so FEX assesses that text itself.
    The call is OUTPUT-source and detect-only: the response is never changed, and only policy and category
    are logged, never the text. A missing configuration or any error is swallowed, so a model call never
    fails because of the assessment.
    """

    def __init__(self, client: Any | None = None, guardrail_id: str | None = None, version: str | None = None):
        self._client = client
        self._id = guardrail_id if guardrail_id is not None else os.environ.get(ENV_ID)
        self._version = version if version is not None else os.environ.get(ENV_VERSION)

    @property
    def configured(self) -> bool:
        return bool(self._id and self._version)

    def _bedrock(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime")
        return self._client

    def assess(self, texts: list[str], conversation_id: str | None) -> None:
        joined = "\n\n".join(t for t in texts if t and t.strip())
        if not joined or not self.configured:
            return
        try:
            response = self._bedrock().apply_guardrail(
                guardrailIdentifier=self._id, guardrailVersion=self._version,
                source="OUTPUT", content=[{"text": {"text": joined}}],
            )
        except Exception:  # noqa: BLE001 - assessment must never break a model call
            log.exception("output guardrail assessment failed for conversation %s", conversation_id)
            return
        # ApplyGuardrail returns a flat list of assessments, not the Converse trace shape.
        for assessment in response.get("assessments") or []:
            for finding in _from_assessment(assessment, "output"):
                log.warning("guardrail_finding %s", json.dumps(
                    {"event": "guardrail_finding", "conversation_id": conversation_id, **finding}))


#: Narrative text to assess, per structured-output model. Only free text a producer could see; never tags,
#: booleans, citations or source identifiers.
def narrative_texts(output: Any) -> list[str]:
    name = type(output).__name__
    if name == "IntakeTurn":
        return [output.reply]
    if name == "PlaybackDraft":
        return [output.text, output.challenge, output.timing, output.severity, output.tried]
    if name == "RecordSummary":
        return [output.summary_original, output.summary_english or ""]
    if name == "ShortReply":
        return [output.reply]
    if name == "AnswerDraft":
        return [c.text for c in [*output.insights, *output.peer_examples]]
    return []


class GuardedBedrockModel(GuardrailFindingsMixin, BedrockModel):
    """The Bedrock model every FEX call uses."""


def guarded_bedrock_model(model_id: str) -> GuardedBedrockModel:
    """A BedrockModel with the Guardrail attached (when configured) and its findings logged."""
    return GuardedBedrockModel(model_id=model_id, **guardrail_settings())
