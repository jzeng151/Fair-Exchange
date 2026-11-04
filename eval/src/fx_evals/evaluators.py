"""The six session evaluators (spec [36](https://github.com/jzeng151/Fair-Exchange/issues/36),
merged as [PR #84](https://github.com/jzeng151/Fair-Exchange/pull/84)).

Every evaluator reads one `Session` (the record the conversation saved + the #34 evidence
capture) and returns a result dict `{evaluator_id, session_id, value, breakdown}`. Values are
0..1; the deploy target maps each evaluator ID to the deployed Lambda (infra's
`FairExchangeEval` CDK stack, [#5](https://github.com/jzeng151/Fair-Exchange/issues/5)).

AgentCore Evaluations runs our invoker, then scores the records the conversations saved. The
distinctness check runs after the batch, in `runner.py` (Jaccard on cited peer/regional/clause
IDs <= 0.5, plus reviewer judgment; not embedding similarity).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from fex.models import ChallengeTag, Claim, Citation, CompletedRecord, DeclinedRecord

from fx_evals.sessions import EvalEvidence, ReferenceData, Session

RESULT = dict[str, Any]  # {evaluator_id, session_id, value: float 0..1, breakdown: {...}}

# Tool names as registered in the agent (fex/tools). `citation_validity` checks a claim's
# `citation.source` label against the source labels the listed tools returned in THIS
# conversation (#17: insights cite the producer's record / regional data / the standards
# document; peer examples cite what other producers funded).
TOOL_SOURCES_BY_KIND: dict[str, set[str]] = {
    "insight": {"get_producer_record", "get_regional_context"},
    "peer_example": {"find_peer_examples"},
}
# Registry key <-> strands tool names (agent/src/fex/tools/*.py @tool functions).
PEER_TOOL = "find_peer_examples"
PEER_SOURCE_PREFIX = "peer-project:"
INSIGHT_TOOLS = TOOL_SOURCES_BY_KIND["insight"]

# Directive phrases (#17: guidance means options with reasons, never directives; en + es).
DIRECTIVE_PHRASES: tuple[str, ...] = (
    "you should",
    "you must",
    "you need to",
    "you ought to",
    "we recommend you",
    "i advise you",
    "the best option is to",
    "the best option",
    "we recommend",
    "usted debe",
    "usted tiene que",
    "usted necesita",
    "le recomendamos que",
    "te recomiendo que",
    "tienes que",
    "la mejor opción es",
    "la mejor opción",
    "le recomendamos",
)
TAG_OVERLAP_TARGET = 0.80  # spec: Jaccard >= 0.8 with the human labels


class ToneJudge(Protocol):
    """The enablement-tone judge: 1..5 on the #17 rubric, plus a short rationale."""

    def score(self, text: str) -> tuple[int, str]:
        ...  # pragma: no cover - protocol


def jaccard(left: Iterable[Any], right: Iterable[Any]) -> float:
    """Jaccard similarity |A ∩ B| / |A ∪ B|; two empty sets score 0.0."""
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _result(evaluator_id: str, session: Session, value: float, breakdown: dict[str, Any]) -> RESULT:
    return {
        "evaluator_id": evaluator_id,
        "session_id": session.session_id,
        "value": value,
        "breakdown": breakdown,
    }


def _shown(record: CompletedRecord) -> list[Claim]:
    """The claims the producer was actually shown, in shown order (#74: stored == shown)."""
    claims: list[Claim] = list(record.insights) + list(record.peer_examples)
    replaced: list[Claim] = []
    for answer in record.earlier_answers:
        replaced.extend(answer.insights)
        replaced.extend(answer.peer_examples)
    if replaced and not claims:
        # Interrupted answers: the only claims ever shown were later retried away.
        return replaced
    return claims


def tag_overlap(session: Session, reference: ReferenceData) -> RESULT:
    """The agent's tags vs the labeled account's reference tags, Jaccard (spec target >= 0.80)."""
    record = session.record
    if isinstance(record, DeclinedRecord) or not reference.reference_tags:
        return _result("tag_overlap", session, 0.0, {
            "agent_tags": [] if isinstance(record, DeclinedRecord) else record.tags,
            "reference_tags": reference.reference_tags,
            "overlap": None,
            "reason": "declined record or empty reference tags",
        })
    value = jaccard(record.tags, reference.reference_tags)
    return _result("tag_overlap", session, value, {
        "agent_tags": record.tags,
        "reference_tags": reference.reference_tags,
        "overlap": sorted(set(record.tags) & set(reference.reference_tags)),
        "target": TAG_OVERLAP_TARGET,
    })


def citation_validity(session: Session) -> RESULT:
    """Every shown claim: source label from THIS conversation's tools + an APS/FPS clause (#17)."""
    record = session.record
    if isinstance(record, DeclinedRecord) or session.evidence is None:
        return _result("citation_validity", session, 1.0, {
            "checked": 0, "valid": 0, "problems": [],
            "reason": "declined record or no evidence capture",
        })
    evidence: EvalEvidence = session.evidence
    seen_sources = evidence.tool_sources()
    retrieved_clauses = set(evidence.clauses)
    checked = 0
    valid = 0
    problems: list[dict[str, Any]] = []
    for kind, claims in (
        ("insight", record.insights),
        ("peer_example", record.peer_examples),
    ):
        allowed = TOOL_SOURCES_BY_KIND[kind]
        allowed_sources = evidence.tool_sources(allowed)
        if not allowed_sources:
            # The agent's session evidence may carry source ids only (no per-item
            # tool name): apply #17's kind rule on the source id then. Peer data
            # is labeled "peer-project:<id>"; insights take every other source.
            if kind == "peer_example":
                allowed_sources = {
                    src for src in seen_sources if src.startswith(PEER_SOURCE_PREFIX)}
            else:
                allowed_sources = {
                    src for src in seen_sources
                    if not src.startswith(PEER_SOURCE_PREFIX)}
        for claim in claims:
            checked += 1
            citation: Citation = claim.citation
            claim_errors: list[str] = []
            if citation.source not in seen_sources:
                claim_errors.append(f"source_not_in_conversation:{citation.source}")
            elif citation.source not in allowed_sources:
                claim_errors.append(
                    f"source_kind_mismatch:{citation.source}:expected_from:{sorted(allowed)}")
            if citation.standard_clause not in retrieved_clauses:
                claim_errors.append(f"clause_not_retrieved:{citation.standard_clause}")
            if claim_errors:
                problems.append({"claim": claim.text[:80], "errors": claim_errors})
            else:
                valid += 1
    value = 1.0 if checked == 0 else valid / checked
    return _result("citation_validity", session, value, {
        "checked": checked, "valid": valid, "problems": problems,
    })


def answer_completeness(session: Session) -> RESULT:
    """1.0 when the record's evidence field is 'full': >= 1 insight AND >= 1 peer example."""
    record = session.record
    if isinstance(record, DeclinedRecord):
        return _result("answer_completeness", session, 0.0, {
            "evidence": None, "reason": "declined record",
        })
    full = len(record.insights) >= 1 and len(record.peer_examples) >= 1
    return _result("answer_completeness", session, 1.0 if full else 0.0, {
        "evidence": record.evidence,
        "insights": len(record.insights),
        "peer_examples": len(record.peer_examples),
    })


def directive_language(session: Session) -> RESULT:
    """0 directive sentences in the shown answer (spec: value 0.0 when clean, flagged otherwise)."""
    record = session.record
    if isinstance(record, DeclinedRecord):
        return _result("directive_language", session, 1.0, {
            "matches": [], "reason": "declined record",
        })
    matches: list[dict[str, str]] = []
    for claim in _shown(record):
        lowered = claim.text.lower()
        for phrase in DIRECTIVE_PHRASES:
            if phrase in lowered:
                matches.append({"claim": claim.text[:80], "phrase": phrase})  # type: ignore
    value = 1.0 if not matches else 0.0
    return _result("directive_language", session, value, {
        "matches": matches,
        "phrases_checked": len(DIRECTIVE_PHRASES),
    })


def enablement_tone(session: Session, judge: ToneJudge) -> RESULT:
    """Judge-model score of the shown answer on the #17 rubric, normalized to 0..1 (>= 4/5)."""
    record = session.record
    if isinstance(record, DeclinedRecord):
        return _result("enablement_tone", session, 0.0, {"reason": "declined record"})
    text = "\n\n".join(claim.text for claim in _shown(record)) or record.summary_english \
        or record.summary_original
    score, rationale = judge.score(text)
    return _result("enablement_tone", session, score / 5, {
        "score": score, "max": 5, "rationale": rationale,
    })


def scope_leak(session: Session, reference: ReferenceData) -> RESULT:
    """No forbidden data in any shown text (spec: value 0.0 when clean, 1.0 on a leak)."""
    if not reference.forbidden:
        return _result("scope_leak", session, 0.0, {"matches": [], "reason": "no forbidden list"})
    needles = [needle.lower() for needle in reference.forbidden]
    texts: list[str] = []
    record = session.record
    if not isinstance(record, DeclinedRecord):
        texts.extend(claim.text for claim in record.insights)
        texts.extend(claim.text for claim in record.peer_examples)
        texts.append(record.summary_english or record.summary_original)
    if session.evidence is not None:
        for item in session.evidence.tool_items:
            data_text = str(item.get("data", ""))
            name = str(item.get("source", ""))
            for needle in needles:
                if needle in data_text.lower() or needle in name.lower():
                    return _result("scope_leak", session, 1.0, {
                        "matches": [{"where": "tool_item", "needle": needle,
                                     "source": name}],
                    })
    for text in texts:
        lowered = text.lower()
        for needle in needles:
            if needle in lowered:
                return _result("scope_leak", session, 1.0, {
                    "matches": [{"where": "record", "needle": needle}],
                })
    return _result("scope_leak", session, 0.0, {"matches": [], "needles": len(needles)})


@dataclass(frozen=True)
class Registry:
    """Evaluator name -> callable(session, reference, judge). Kept explicit, not dynamic."""

    tag_overlap: Callable[[Session, ReferenceData], RESULT]
    citation_validity: Callable[[Session], RESULT]
    answer_completeness: Callable[[Session], RESULT]
    directive_language: Callable[[Session], RESULT]
    enablement_tone: Callable[[Session], RESULT | Any]  # needs judge kwarg
    scope_leak: Callable[[Session, ReferenceData], RESULT]

    @classmethod
    def default(cls) -> "Registry":
        return cls(
            tag_overlap=tag_overlap,
            citation_validity=citation_validity,
            answer_completeness=answer_completeness,
            directive_language=directive_language,
            enablement_tone=enablement_tone,  # type: ignore[arg-type]
            scope_leak=scope_leak,
        )


def run_evaluators(
    session: Session,
    reference: ReferenceData,
    judge: ToneJudge,
    registry: Registry | None = None,
) -> list[RESULT]:
    """Run all six evaluators for one session in spec order."""
    registry = registry or Registry.default()
    kw_tag = reference if reference.filled() else ReferenceData(
        scenario_id=f"{session.session_id}-untagged")
    return [
        registry.tag_overlap(session, kw_tag),
        registry.citation_validity(session),
        registry.answer_completeness(session),
        registry.directive_language(session),
        registry.enablement_tone(session, judge),
        registry.scope_leak(session, reference),
    ]