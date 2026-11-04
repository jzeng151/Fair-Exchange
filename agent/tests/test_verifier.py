"""Issue #17: deterministic citation verifier.

Team decision: after generation, every cited source must have been returned by a tool this
session, every clause ID must exist in APS/FPS, and failures regenerate.
"""
import pytest
from fx_data.standards import Standards

from fex.models import Claim
from fex.verifier import GroundedAnswer, SessionEvidence, generate_verified, verify

CHIRPS = "CHIRPS rainfall (Cauca, 2024-2025)"
PEER = "FTUSA Premium project record P-0042"


@pytest.fixture(scope="module")
def standards():
    return Standards.load()


def claim(text, source, clause):
    return Claim.model_validate({"text": text, "citation": {"source": source, "standard_clause": clause}})


@pytest.fixture
def evidence():
    ev = SessionEvidence()
    ev.record(CHIRPS)
    ev.record(PEER)
    return ev


def test_claim_from_a_tool_with_a_real_clause_passes(evidence, standards):
    result = verify([claim("Rainfall was 22% below average.", CHIRPS, "APS 3.6.1")], [], evidence, standards)
    assert result.ok
    assert result.problems == []


def test_source_no_tool_returned_this_session_is_flagged(evidence, standards):
    invented = claim("Prices will rise next year.", "Market forecast 2027", "APS 3.6.1")
    result = verify([invented], [], evidence, standards)
    assert not result.ok
    assert "Market forecast 2027" in result.problems[0].reason


def test_clause_that_is_not_in_aps_or_fps_is_flagged(evidence, standards):
    fake_clause = claim("Rainfall was low.", CHIRPS, "APS 9.9.9")
    result = verify([fake_clause], [], evidence, standards)
    assert not result.ok
    assert "APS 9.9.9" in result.problems[0].reason


def test_problem_says_which_claim_failed(evidence, standards):
    good = claim("A cooperative funded rainwater catchment.", PEER, "APS 3.6.1")
    bad = claim("Another group funded wells.", "Unknown project", "APS 3.6.1")
    result = verify([], [good, bad], evidence, standards)
    assert [(p.section, p.index) for p in result.problems] == [("peer_examples", 1)]


def test_a_claim_with_two_problems_reports_both(evidence, standards):
    result = verify([claim("Made up.", "Nowhere", "FPS 99.1")], [], evidence, standards)
    assert len(result.problems) == 2


def test_session_evidence_learns_sources_from_tool_results(standards):
    ev = SessionEvidence()
    ev.record_tool_result([{"project": "Rainwater tanks", "source": PEER}, {"source": CHIRPS}])
    result = verify([claim("Rainfall was low.", CHIRPS, "APS 3.6.1")], [], ev, standards)
    assert result.ok


GOOD = ("Rainfall was 22% below average.", CHIRPS, "APS 3.6.1")
BAD = ("Prices will double.", "Made-up forecast", "APS 3.6.1")


class FakeWriter:
    """Stands in for FEX writing an answer. Returns scripted answers and records what it was told."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, problems):
        self.calls.append(problems)
        insights = self.answers[min(len(self.calls), len(self.answers)) - 1]
        return GroundedAnswer(insights=[claim(*c) for c in insights], peer_examples=[])


def test_a_verified_first_answer_is_used_as_is(evidence, standards):
    writer = FakeWriter([GOOD])
    result = generate_verified(writer, evidence, standards)
    assert result.attempts == 1
    assert writer.calls == [None]  # first attempt is not told about any problems
    assert [c.text for c in result.answer.insights] == [GOOD[0]]


def test_failed_verification_regenerates_and_tells_the_writer_what_was_wrong(evidence, standards):
    writer = FakeWriter([BAD], [GOOD])
    result = generate_verified(writer, evidence, standards)
    assert result.attempts == 2
    assert "Made-up forecast" in writer.calls[1][0].reason
    assert result.removed == []


def test_gives_up_after_the_retry_limit(evidence, standards):
    writer = FakeWriter([GOOD, BAD])
    result = generate_verified(writer, evidence, standards, max_retries=2)
    assert result.attempts == 3  # 1 try + 2 retries, then stop


def test_unverified_claims_never_reach_the_producer(evidence, standards):
    writer = FakeWriter([GOOD, BAD])
    result = generate_verified(writer, evidence, standards, max_retries=2)
    assert [c.text for c in result.answer.insights] == [GOOD[0]]
    assert [p.claim_text for p in result.removed] == [BAD[0]]
    assert verify(result.answer.insights, result.answer.peer_examples, evidence, standards).ok
