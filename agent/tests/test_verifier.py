"""Issue #17: deterministic citation verifier. Spec: docs/specs/17-standards-grounding.md.

A claim passes only if its source was returned by a data tool this session and is the right kind for its
section, its clause exists in APS/FPS and was returned by the standards tool, and it uses no directive
language. Failures regenerate; claims that still fail are dropped.
"""
import pytest
from fx_data.standards import Standards

from fex.models import Claim
from fex.tone import DIRECTIVE_PHRASES, find_directive
from fex.verifier import GroundedAnswer, SessionEvidence, check_claim, generate_verified, verify

CHIRPS = "CHIRPS v2.0 rainfall anomaly, Cauca, 2024-2025 [RF-0142]"
PEER = "Premium project, Cooperativa Ejemplo [PC-0042]"
RECORD = "Your Premium project: Water tanks [PRJ-7]"
RETRIEVED = "APS 3.6.1"
NOT_RETRIEVED = "APS 1.1"  # a real clause the standards tool did not return


@pytest.fixture(scope="module")
def standards():
    return Standards.load()


def claim(text, source, clause=RETRIEVED):
    return Claim.model_validate({"text": text, "citation": {"source": source, "standard_clause": clause}})


def item(source, kind, **data):
    return {"source": source, "kind": kind, "text": "t", "period": None, "strength": "exact", "data": data}


@pytest.fixture
def evidence():
    ev = SessionEvidence()
    ev.record_tool_result([item(CHIRPS, "regional"), item(PEER, "peer"), item(RECORD, "producer_record"),
                           item(RETRIEVED, "standard", clause_id=RETRIEVED, standard="APS")])
    return ev


def codes(result):
    return [p.code for p in result.problems]


# ------------------------------------------------------------------ sources

def test_claim_from_a_tool_with_a_retrieved_clause_passes(evidence, standards):
    result = verify([claim("Rainfall was 22% below average.", CHIRPS)], [], evidence, standards)
    assert result.ok and result.problems == []


def test_source_no_tool_returned_this_session_is_flagged(evidence, standards):
    result = verify([claim("Prices will rise next year.", "Market forecast 2027")], [], evidence, standards)
    assert codes(result) == ["unknown_source"]
    assert "Market forecast 2027" in result.problems[0].reason


@pytest.mark.parametrize("source", [CHIRPS, RECORD])
def test_insights_may_cite_regional_or_producer_record_sources(evidence, standards, source):
    assert verify([claim("A fact.", source)], [], evidence, standards).ok


def test_an_insight_citing_a_peer_source_fails_with_wrong_source_kind(evidence, standards):
    result = verify([claim("A peer built tanks.", PEER)], [], evidence, standards)
    assert codes(result) == ["wrong_source_kind"]


def test_a_peer_example_citing_a_regional_source_fails_with_wrong_source_kind(evidence, standards):
    result = verify([], [claim("Rainfall fell.", CHIRPS)], evidence, standards)
    assert codes(result) == ["wrong_source_kind"]


def test_a_claim_citing_a_standard_as_its_source_fails(evidence, standards):
    assert codes(verify([claim("A clause.", RETRIEVED)], [], evidence, standards)) == ["wrong_source_kind"]


# ------------------------------------------------------------------ clauses

def test_clause_that_is_not_in_aps_or_fps_is_flagged(evidence, standards):
    result = verify([claim("Rainfall was low.", CHIRPS, "APS 9.9.9")], [], evidence, standards)
    assert codes(result) == ["unknown_clause"]
    assert "APS 9.9.9" in result.problems[0].reason


def test_a_real_clause_the_standards_tool_did_not_return_fails(evidence, standards):
    assert standards.exists(NOT_RETRIEVED)
    result = verify([claim("Rainfall was low.", CHIRPS, NOT_RETRIEVED)], [], evidence, standards)
    assert codes(result) == ["clause_not_retrieved"]


def test_a_returned_clause_passes_whatever_its_spacing_or_case(evidence, standards):
    assert verify([claim("Rainfall was low.", CHIRPS, " aps  3.6.1 ")], [], evidence, standards).ok


def test_standards_items_add_their_clause_ids_to_the_session_evidence():
    ev = SessionEvidence()
    ev.record_tool_result([item("APS 2.1.1", "standard", clause_id="aps 2.1.1", standard="APS")])
    assert ev.clauses == {"APS 2.1.1"} and ev.kind_of("APS 2.1.1") == "standard"


# ------------------------------------------------------------------ directive language

@pytest.mark.parametrize("text", [
    "You should build water tanks.", "We recommend drip irrigation.", "This is the best option for you.",
    "Usted debe construir tanques.", "Le recomendamos el riego por goteo.", "Es la mejor opción.",
    "Es la mejor opcion.",  # accents dropped
    "YOU SHOULD act now.",
])
def test_a_directive_phrase_in_english_or_spanish_fails(evidence, standards, text):
    result = verify([claim(text, CHIRPS)], [], evidence, standards)
    assert codes(result) == ["directive_language"]
    assert result.problems[0].reason.startswith("directive language")


@pytest.mark.parametrize("text", [
    "Rainfall in Cauca was 11.5% below average in 2024-2025.",
    "A cooperative in Caldas funded watershed conservation.",
    "La lluvia bajó un 11,5 % en 2024-2025.",
    "Shoulders of the road flooded.",  # "should" inside another word is not a phrase
])
def test_neutral_statements_pass_the_tone_check(text):
    assert find_directive(text) is None


def test_every_listed_phrase_is_detected():
    for phrases in DIRECTIVE_PHRASES.values():
        for phrase in phrases:
            assert find_directive(f"Una frase: {phrase} algo.") == phrase


# ------------------------------------------------------------------ per-claim and whole-answer checks

def test_problem_says_which_claim_failed(evidence, standards):
    good = claim("A cooperative funded rainwater catchment.", PEER)
    bad = claim("Another group funded wells.", "Unknown project")
    result = verify([], [good, bad], evidence, standards)
    assert [(p.section, p.index, p.code) for p in result.problems] == [("peer_examples", 1, "unknown_source")]


def test_a_claim_with_several_problems_reports_each_code(evidence, standards):
    result = verify([claim("You should do this.", "Nowhere", "FPS 99.1")], [], evidence, standards)
    assert codes(result) == ["unknown_source", "unknown_clause", "directive_language"]


def test_the_per_claim_check_and_the_whole_answer_check_agree(evidence, standards):
    insights = [claim("Rainfall fell.", CHIRPS), claim("A peer built tanks.", PEER),
                claim("Rain.", CHIRPS, NOT_RETRIEVED), claim("You should save water.", RECORD)]
    peers = [claim("A peer built tanks.", PEER), claim("Invented.", "Nowhere", "APS 9.9.9")]
    whole = verify(insights, peers, evidence, standards).problems
    one_by_one = [p for section, claims in (("insights", insights), ("peer_examples", peers))
                  for i, c in enumerate(claims) for p in check_claim(section, c, evidence, standards, i)]
    assert whole == one_by_one
    assert {p.code for p in whole} == {"wrong_source_kind", "clause_not_retrieved", "directive_language",
                                       "unknown_source", "unknown_clause"}


# ------------------------------------------------------------------ regenerate on failure

GOOD = ("Rainfall was 22% below average.", CHIRPS)
BAD = ("Prices will double.", "Made-up forecast")


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
    assert writer.calls[1][0].code == "unknown_source" and "Made-up forecast" in writer.calls[1][0].reason
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
