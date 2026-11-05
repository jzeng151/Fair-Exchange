"""FEX eval package (issue #36): six session evaluators, the judge model, the scenario
invoker (the [#35](https://github.com/jzeng151/Fair-Exchange/issues/35) runner) and the
on-demand AgentCore Evaluations runner.

Spec: docs/specs/36-eval-harness.md.
"""
from fex.tone import DIRECTIVE_PHRASES  # one shared phrase list with the agent (#17/#36)
from fx_evals.evaluators import (
    RESULT,
    TAG_OVERLAP_TARGET,
    Registry,
    answer_completeness,
    citation_validity,
    directive_language,
    enablement_tone,
    jaccard,
    scope_leak,
    tag_overlap,
)
from fx_evals.sessions import (
    EVIDENCE_BUCKET_ENV,
    RECORDS_TABLE_ENV,
    EvalEvidence,
    ReferenceData,
    Session,
    load_sessions,
)

EVALUATOR_IDS = (
    "tag_overlap",
    "citation_validity",
    "answer_completeness",
    "directive_language",
    "enablement_tone",
    "scope_leak",
)

__all__ = [
    "DIRECTIVE_PHRASES",
    "EVALUATOR_IDS",
    "EVIDENCE_BUCKET_ENV",
    "RECORDS_TABLE_ENV",
    "RESULT",
    "TAG_OVERLAP_TARGET",
    "EvalEvidence",
    "ReferenceData",
    "Registry",
    "Session",
    "answer_completeness",
    "citation_validity",
    "directive_language",
    "enablement_tone",
    "jaccard",
    "load_sessions",
    "scope_leak",
    "tag_overlap",
]