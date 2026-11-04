"""Bedrock Guardrail findings (issue #12). Spec: docs/specs/12-guardrail.md.

The Guardrail runs in detect mode on every model call: every action is NONE and redaction is off, so it never
blocks or alters anything. Bedrock returns its assessment in the stream's `metadata.trace.guardrail`. This
module logs each detected finding to CloudWatch (logger `fex.guardrail`) with the conversation ID, the policy
type and the topic or category ONLY, never text: assessments can carry matched text (word and PII matches),
which is never read here. Findings are not written to the record (#21 keeps misdirected requests out of it).
"""
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from strands.models.model import Model

log = logging.getLogger("fex.guardrail")

# For each policy in an assessment: the list holding its items, and the field that names an item.
# Matched text (e.g. "match") is deliberately never listed here.
_POLICIES = {
    "topicPolicy": [("topics", "name")],
    "contentPolicy": [("filters", "type")],
    "wordPolicy": [("customWords", None), ("managedWordLists", "type")],
    "sensitiveInformationPolicy": [("piiEntities", "type"), ("regexes", "name")],
    "contextualGroundingPolicy": [("filters", "type")],
}


def _detected(item: dict) -> bool:
    return item.get("detected") is True or item.get("action") not in (None, "NONE")


def _from_assessment(source: str, assessment: dict) -> list[dict]:
    found = []
    for policy, lists in _POLICIES.items():
        for list_name, name_field in lists:
            for item in (assessment.get(policy) or {}).get(list_name, []) or []:
                if _detected(item):
                    name = item.get(name_field) if name_field else list_name
                    found.append({"source": source, "policy": policy, "name": str(name or list_name)})
    return found


def findings(trace: dict | None) -> list[dict]:
    """Detected findings in a Guardrail trace: source (input/output), policy type and topic or category."""
    if not trace:
        return []
    found = []
    for assessment in (trace.get("inputAssessment") or {}).values():
        found += _from_assessment("input", assessment)
    for assessments in (trace.get("outputAssessments") or {}).values():
        for assessment in assessments or []:
            found += _from_assessment("output", assessment)
    return found


def log_findings(trace: dict | None, conversation_id: str) -> None:
    for finding in findings(trace):
        log.info(json.dumps({"conversation_id": conversation_id, **finding}, sort_keys=True))


class GuardrailObserved(Model):
    """Wraps a model for one conversation: passes every stream event through unchanged and logs any Guardrail
    findings in `metadata` events. It observes only; it never changes what the model returns."""

    def __init__(self, inner: Any, conversation_id: str) -> None:
        self.inner, self.conversation_id = inner, conversation_id

    def update_config(self, **model_config: Any) -> None:
        self.inner.update_config(**model_config)

    def get_config(self) -> Any:
        return self.inner.get_config()

    def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        return self.inner.structured_output(*args, **kwargs)

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async for event in self.inner.stream(*args, **kwargs):
            if isinstance(event, dict) and "metadata" in event:
                try:
                    log_findings((event["metadata"].get("trace") or {}).get("guardrail"), self.conversation_id)
                except Exception:  # noqa: BLE001 - logging must never affect the conversation
                    logging.getLogger(__name__).exception("could not read a Guardrail trace")
            yield event


class ApplyGuardrailCheck:
    """Checks FEX's own producer-facing words with the Guardrail (ApplyGuardrail, source OUTPUT) and logs findings.

    Needed because FEX's replies, playback and claims come back as structured output, i.e. tool-call input,
    which Bedrock does not assess with an attached Guardrail. Detect only: it never changes what was shown,
    and a failed check is logged, never raised.
    """

    def __init__(self, client: Any, guardrail_id: str, version: str) -> None:
        self.client, self.guardrail_id, self.version = client, guardrail_id, version

    def __call__(self, texts: list[str], conversation_id: str) -> None:
        content = [{"text": {"text": t}} for t in texts if t and t.strip()]
        if not content:
            return
        response = self.client.apply_guardrail(guardrailIdentifier=self.guardrail_id,
                                               guardrailVersion=self.version, source="OUTPUT", content=content)
        log_findings({"outputAssessments": {self.guardrail_id: response.get("assessments", [])}}, conversation_id)
