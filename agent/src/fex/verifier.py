"""Deterministic citation verifier (issue #17). Spec: docs/specs/17-standards-grounding.md.

Runs on every claim before the producer sees it. A claim passes only if:
  1. its source was returned by a data tool in this conversation (nothing invented);
  2. that source is the right kind for its section: insights cite the producer's record or regional data,
     peer examples cite a peer project;
  3. its clause exists in APS or FPS, and
  4. the standards tool returned that clause in this conversation (not merely any real clause);
  5. its text uses no directive language (fex.tone).
No model is involved. This proves provenance, not that the wording matches the fact or that the clause is
the best fit; evals and the FTUSA reviewer check those.
"""
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

from fx_data.standards import Standards, normalize_id
from pydantic import BaseModel, Field

from fex.models import Claim
from fex.tone import find_directive

log = logging.getLogger(__name__)

SourceKind = Literal["producer_record", "regional", "peer", "standard"]
Section = Literal["insights", "peer_examples"]
ReasonCode = Literal["unknown_source", "wrong_source_kind", "unknown_clause", "clause_not_retrieved",
                     "directive_language", "malformed"]

ALLOWED_KINDS: dict[str, frozenset[str]] = {
    "insights": frozenset({"producer_record", "regional"}),
    "peer_examples": frozenset({"peer"}),
}


@dataclass
class SessionEvidence:
    """What the data tools returned in this conversation. Each tool adds its items as it returns them."""

    sources: dict[str, SourceKind] = field(default_factory=dict)  # source label -> kind
    clauses: set[str] = field(default_factory=set)  # clause IDs the standards tool returned

    def record(self, source: str, kind: SourceKind) -> None:
        if source and source.strip():
            self.sources[source.strip()] = kind

    def record_clause(self, clause_id: str) -> None:
        if normalized := normalize_id(clause_id):
            self.clauses.add(normalized)

    def record_tool_result(self, items: Iterable[dict]) -> None:
        """Record every item's `source` with its `kind`; standards items also add their clause ID."""
        for item in items:
            self.record(item.get("source", ""), item["kind"])
            if item["kind"] == "standard":
                self.record_clause((item.get("data") or {}).get("clause_id", ""))

    def kind_of(self, source: str) -> SourceKind | None:
        return self.sources.get((source or "").strip())

    def __contains__(self, source: str) -> bool:
        return self.kind_of(source) is not None


@dataclass(frozen=True)
class Problem:
    section: str  # "insights" or "peer_examples"
    index: int  # position of the claim within its section
    claim_text: str
    code: ReasonCode
    reason: str  # readable; the decision log keeps only `code`


@dataclass
class Verification:
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_claim(section: Section, claim: Claim, evidence: SessionEvidence, standards: Standards,
                index: int = 0) -> list[Problem]:
    """Check one claim on its own, so an answer can be checked and streamed claim by claim (#13, #18)."""
    problems = []

    def fail(code: ReasonCode, reason: str) -> None:
        problems.append(Problem(section, index, claim.text, code, reason))

    source, clause = claim.citation.source, claim.citation.standard_clause
    kind = evidence.kind_of(source)
    if kind is None:
        fail("unknown_source", f"source '{source}' was not returned by any tool in this session")
    elif kind not in ALLOWED_KINDS[section]:
        fail("wrong_source_kind", f"{section} cannot cite a {kind} source ('{source}')")
    if not standards.exists(clause):
        fail("unknown_clause", f"cites '{clause}', which is not an APS or FPS clause")
    elif normalize_id(clause) not in evidence.clauses:
        fail("clause_not_retrieved", f"cites '{clause}', which the standards lookup did not return")
    if phrase := find_directive(claim.text):
        fail("directive_language", f"directive language ('{phrase}')")
    return problems


def malformed(section: str, index: int, text: str, detail: str) -> Problem:
    """A claim line that is not valid JSON or not the claim shape (#18)."""
    return Problem(section, index, text, "malformed", f"malformed claim: {detail}")


def verify(insights: list[Claim], peer_examples: list[Claim],
           evidence: SessionEvidence, standards: Standards) -> Verification:
    """Check every claim. Returns every problem found, not just the first."""
    problems = []
    for section, claims in (("insights", insights), ("peer_examples", peer_examples)):
        for index, claim in enumerate(claims):
            problems += check_claim(section, claim, evidence, standards, index)
    return Verification(problems)


class GroundedAnswer(BaseModel):
    """What FEX tells the producer: what the data shows, and what others have tried."""

    insights: list[Claim] = Field(default_factory=list)
    peer_examples: list[Claim] = Field(default_factory=list)


@dataclass
class VerifiedAnswer:
    answer: GroundedAnswer  # only verified claims
    attempts: int
    removed: list[Problem] = field(default_factory=list)  # claims dropped after the last retry


def generate_verified(write: Callable[[list[Problem] | None], GroundedAnswer], evidence: SessionEvidence,
                      standards: Standards, max_retries: int = 2) -> VerifiedAnswer:
    """Write an answer, verify it, and regenerate with the problems listed if it fails.

    `write(problems)` produces an answer; `problems` is None on the first attempt and the list of
    problems from the previous attempt on retries. After `max_retries` failed retries, unverified
    claims are removed (and their reason codes logged) so they never reach the producer.
    """
    problems = None
    for attempt in range(1, max_retries + 2):
        answer = write(problems)
        result = verify(answer.insights, answer.peer_examples, evidence, standards)
        if result.ok:
            return VerifiedAnswer(answer, attempt)
        problems = result.problems

    failed = {(p.section, p.index) for p in problems}
    kept = GroundedAnswer(
        insights=[c for i, c in enumerate(answer.insights) if ("insights", i) not in failed],
        peer_examples=[c for i, c in enumerate(answer.peer_examples) if ("peer_examples", i) not in failed],
    )
    for p in problems:
        log.warning("removed unverified claim (%s #%d): %s", p.section, p.index, p.code)
    return VerifiedAnswer(kept, attempt, problems)
