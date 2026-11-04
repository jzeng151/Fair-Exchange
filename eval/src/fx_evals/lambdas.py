"""The six code-based evaluators as Lambda handlers (spec [36](https://github.com/jzeng151/Fair-Exchange/issues/36)).

One handler each; infra's `FairExchangeEval` CDK stack ([#5](https://github.com/jzeng151/Fair-Exchange/issues/5))
zips this package and wires the evaluator registry to these handlers. Payload:

```json
{"session_id": "<record table lookup>",
 "reference": {"scenario_id": "...", "reference_tags": [...], "forbidden": [...]}}
```

Response: the evaluator result dict `{evaluator_id, session_id, value, breakdown}`.
"""
from __future__ import annotations

from typing import Any

from fx_evals.evaluators import (
    Registry,
    answer_completeness,
    citation_validity,
    directive_language,
    enablement_tone,
    scope_leak,
    tag_overlap,
)
from fx_evals.judge import BedrockToneJudge
from fx_evals.sessions import (
    EvalEvidence,
    ReferenceData,
    Session,
    evidence_bucket_from_env,
    records_table_from_env,
)

_registry = Registry.default()
_records: dict[str, Any] = {}  # wired by infra's CDK stack before the Lambdas run
_records_table = None
_evidence: Any = None
_judge: Any = None


def _session(payload: dict[str, Any], session_id: str) -> Session:
    global _records_table, _evidence
    if _records_table is None:
        _records_table = records_table_from_env()
    record = _records.get(session_id) or _records_table.get(session_id)
    evidence = payload.get("evidence")
    if evidence is None:
        # Spec 36: the evidence capture lives in the eval evidence bucket (env),
        # the way the record lives in the records table; payloads may omit it.
        if _evidence is None:
            _evidence = evidence_bucket_from_env()
        evidence = _evidence.get(session_id)
    return Session(
        session_id=session_id,
        record=record,
        evidence=EvalEvidence.model_validate(evidence) if evidence else None,
    )


def _reference(payload: dict[str, Any]) -> ReferenceData:
    return ReferenceData.model_validate(payload.get("reference") or {})


def _run(evaluator_id: str, payload: dict[str, Any], runner: Any, needs_reference: bool = True
         ) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "")
    session = _session(payload, session_id)
    reference = _reference(payload)
    result = runner(session, reference) if needs_reference else runner(session)
    assert result["evaluator_id"] == evaluator_id, "evaluator id must match its handler"
    return result


def handler_tag_overlap(payload: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return _run("tag_overlap", payload, _registry.tag_overlap)


def handler_citation_validity(payload: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return _run("citation_validity", payload, _registry.citation_validity, needs_reference=False)


def handler_answer_completeness(payload: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return _run("answer_completeness", payload, _registry.answer_completeness,
                needs_reference=False)


def handler_directive_language(payload: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return _run("directive_language", payload, _registry.directive_language,
                needs_reference=False)


def handler_enablement_tone(payload: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    global _judge
    if _judge is None:
        _judge = judge_for_handler()
    return _run("enablement_tone", payload,
                lambda session, _reference: enablement_tone(session, _judge),
                needs_reference=False)


def judge_for_handler() -> Any:
    """The judge model, built from the stack's env (a stub judge in tests)."""
    try:
        return BedrockToneJudge.from_env()
    except AssertionError:
        raise  # infra must set EVAL_JUDGE_MODEL_ID; the Lambda cannot score without it


def handler_scope_leak(payload: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    return _run("scope_leak", payload, _registry.scope_leak)


HANDLERS = {
    "tag_overlap": handler_tag_overlap,
    "citation_validity": handler_citation_validity,
    "answer_completeness": handler_answer_completeness,
    "directive_language": handler_directive_language,
    "enablement_tone": handler_enablement_tone,
    "scope_leak": handler_scope_leak,
}