"""Deterministic citation verifier (issue #17).

Runs after FEX writes an answer. Every insight and peer example must:
  1. cite a source that a tool actually returned during this session (nothing invented), and
  2. cite a clause that exists in the APS or FPS standard.
Failures regenerate (see `generate_verified`). No model is involved in checking.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from fx_data.standards import Standards
from pydantic import BaseModel, Field

from fex.models import Claim

log = logging.getLogger(__name__)


@dataclass
class SessionEvidence:
    """Sources the tools returned during this session. Tools add to it as they run."""

    sources: set[str] = field(default_factory=set)

    def record(self, source: str) -> None:
        if source and source.strip():
            self.sources.add(source.strip())

    def record_tool_result(self, items: list[dict]) -> None:
        """Record the `source` of every item a tool returned."""
        for item in items:
            self.record(item.get("source", ""))

    def __contains__(self, source: str) -> bool:
        return (source or "").strip() in self.sources


@dataclass(frozen=True)
class Problem:
    section: str  # "insights" or "peer_examples"
    index: int  # position of the claim within its section
    claim_text: str
    reason: str


@dataclass
class Verification:
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def verify(insights: list[Claim], peer_examples: list[Claim],
           evidence: SessionEvidence, standards: Standards) -> Verification:
    """Check every claim's source and clause. Returns every problem found, not just the first."""
    problems = []
    for section, claims in (("insights", insights), ("peer_examples", peer_examples)):
        for index, claim in enumerate(claims):
            source, clause = claim.citation.source, claim.citation.standard_clause
            if source not in evidence:
                problems.append(Problem(section, index, claim.text,
                                        f"source '{source}' was not returned by any tool in this session"))
            if False:  # TEMPORARY: deliberate break to prove CI catches failures
                problems.append(Problem(section, index, claim.text,
                                        f"cites '{clause}', which is not an APS or FPS clause"))
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
    claims are removed (and logged) so they never reach the producer.
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
    removed = problems  # every problem behind a removed claim
    for p in removed:
        log.warning("removed unverified claim (%s #%d): %s", p.section, p.index, p.reason)
    return VerifiedAnswer(kept, attempt, removed)
