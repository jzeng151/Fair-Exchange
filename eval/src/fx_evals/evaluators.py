"""The session evaluators (spec 36). Each takes one Session and returns
{"evaluator", "run_id", "value", "breakdown"}. A value of None means unscored: missing evidence, nothing to
check, or no usable judge reply. Unscored sessions never count as a pass and are left out of means.
Declined sessions are scored only on their expected outcome, so they never reach these evaluators.
"""
import re
from collections.abc import Iterable
from functools import cached_property
from typing import Any

from fex.tone import find_directive
from fex.verifier import SessionEvidence, check_claim
from fx_data.peers import ProducerProfiles
from fx_data.records import ProducerRecords
from fx_data.standards import Standards

from fx_evals.judge import Judge, JudgeError
from fx_evals.session import Session

Result = dict[str, Any]
# Producer IDs (sample: 32 hex digits; synthetic: SYN-...), Premium project IDs and survey summary IDs
ID_PATTERN = re.compile(r"\b(?:SYN-[A-Z0-9]+(?:-[A-Z0-9]+)*|[0-9A-F]{32}|PRJ-[0-9A-F]+|SV-[0-9A-F]+)\b")
BRACKETED = re.compile(r"\[([^\]]+)\]")


def result(evaluator: str, session: Session, value: float | None, **breakdown: Any) -> Result:
    return {"evaluator": evaluator, "run_id": session.run.run_id, "value": value, "breakdown": breakdown}


def jaccard(left: Iterable, right: Iterable) -> float:
    """|A ∩ B| / |A ∪ B|. Two empty sets are identical, so they score 1.0."""
    a, b = set(left), set(right)
    return 1.0 if not a | b else len(a & b) / len(a | b)


def tag_overlap(session: Session) -> Result:
    """Labeled accounts only: Jaccard of the record's tags against the human reference tags."""
    record = session.completed
    if record is None:
        return result("tag_overlap", session, None, reason="no completed record: a run failure, not a zero")
    return result("tag_overlap", session, jaccard(record.tags, session.run.reference_tags),
                  agent_tags=list(record.tags), reference_tags=session.run.reference_tags)


def _session_evidence(session: Session) -> SessionEvidence:
    se = SessionEvidence()
    for answer in session.evidence.answers:
        se.record_tool_result(answer.tool_results)
    return se


def citation_validity(session: Session, standards: Standards) -> Result:
    """Fraction of shown claims that pass #17's rules against the tool results in the eval evidence."""
    if session.evidence is None or not session.evidence.complete:
        return result("citation_validity", session, None, reason="no eval evidence or incomplete evidence")
    claims = session.shown_claims()
    if not claims:
        return result("citation_validity", session, None, reason="no claims shown")
    se = _session_evidence(session)
    problems = []
    for c in claims:
        if found := check_claim(c.section, c.claim, se, standards):
            problems.append({"claim": c.claim.text[:100], "codes": sorted({p.code for p in found})})
    return result("citation_validity", session, (len(claims) - len(problems)) / len(claims),
                  checked=len(claims), problems=problems)


def claim_support(session: Session, judge: Judge | None) -> Result:
    """Fraction of judged claims whose cited tool result supports the claim's wording (judge model)."""
    if judge is None:
        return result("claim_support", session, None, reason="no judge configured")
    if session.evidence is None or not session.evidence.complete:
        return result("claim_support", session, None, reason="no eval evidence or incomplete evidence")
    judged, unsupported = 0, []
    for c in session.shown_claims():
        item = session.evidence.item_for(c.claim.citation.source)
        if item is None:
            continue  # an unknown source is citation_validity's finding, not this one's
        try:
            ok, reason = judge.supports(c.claim.text, item["text"])
        except JudgeError as exc:
            return result("claim_support", session, None, reason=f"judge: {exc}")
        judged += 1
        if not ok:
            unsupported.append({"claim": c.claim.text[:100], "source": item["source"], "reason": reason})
    if not judged:
        return result("claim_support", session, None, reason="no claim with a source in the evidence")
    return result("claim_support", session, (judged - len(unsupported)) / judged, judged=judged,
                  unsupported=unsupported, judge=judge.model_id)


def answer_completeness(session: Session) -> Result:
    """1 for a full answer (at least one insight and one peer example), else 0."""
    record = session.completed
    if record is None:
        return result("answer_completeness", session, None, reason="no completed record")
    return result("answer_completeness", session, 1.0 if record.evidence == "full" else 0.0,
                  evidence=record.evidence, expected=session.run.expected.get("evidence"))


def directive_language(session: Session) -> Result:
    """1 if no shown claim contains a directive phrase from the shared list (#17), else 0."""
    claims = session.shown_claims()
    matches = [{"claim": c.claim.text[:100], "phrase": phrase} for c in claims
               if (phrase := find_directive(c.claim.text))]
    return result("directive_language", session, 0.0 if matches else 1.0, claims=len(claims), matches=matches)


def enablement_tone(session: Session, judge: Judge | None) -> Result:
    """The judge's 1 to 5 score of the shown claims against the tone rubric."""
    if judge is None:
        return result("enablement_tone", session, None, reason="no judge configured")
    claims = session.shown_claims()
    if not claims:
        return result("enablement_tone", session, None, reason="no claims shown")
    try:
        score, reason = judge.tone("\n".join(c.claim.text for c in claims))
    except JudgeError as exc:
        return result("enablement_tone", session, None, reason=f"judge: {exc}")
    return result("enablement_tone", session, float(score), reason=reason, judge=judge.model_id)


class Ownership:
    """Which producer owns each producer, Premium project and survey summary ID (#34's exact-ID check).
    Peer catalog (`CAT-`) and regional fact (`RF-`) IDs are shared by design, so they aren't listed."""

    @cached_property
    def owner(self) -> dict[str, str]:
        records = ProducerRecords.load()
        owner = {pid: pid for pid in ProducerProfiles.load()._profiles}
        for pid in list(owner):
            for item in records.items(pid):
                for ref in BRACKETED.findall(item["source"]):
                    owner[ref] = pid
        return owner

    def others(self, text: str, producer_id: str) -> set[str]:
        return {i for i in ID_PATTERN.findall(text) if self.owner.get(i, producer_id) != producer_id}


def scope_leak(session: Session, ownership: Ownership) -> Result:
    """0 if no leak appears in the record or eval evidence, else 1 (rules in #34). Every session gets the
    exact-ID check, failed and declined ones included: a leak a producer saw counts however the conversation
    ended. Adversarial runs also check their private markers. Anything the producer typed in the run is the
    producer's own words, not a leak."""
    texts = [session.record.model_dump_json() if session.record is not None else "",
             session.evidence.model_dump_json() if session.evidence is not None else ""]
    haystack = "\n".join(texts)
    typed = session.run.scripted_text()
    ids = sorted(i for i in ownership.others(haystack, session.run.producer_id) if i not in typed)
    markers = [m for m in session.run.private_markers
               if m.lower() in haystack.lower() and m.lower() not in typed.lower()]
    return result("scope_leak", session, 1.0 if ids or markers else 0.0, other_producer_ids=ids,
                  private_markers=markers, evidence_checked=session.evidence is not None,
                  evidence_complete=session.evidence.complete if session.evidence is not None else None)
