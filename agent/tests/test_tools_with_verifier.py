"""Data tools feed the citation verifier (#17): each tool adds its items to the session evidence as it
returns them, so claims built from those items pass and anything else fails."""
from fx_data.peers import ProducerProfiles
from fx_data.standards import Standards
from tests.conversation_harness import FakeRetriever
from tests.tool_harness import call_tool

from fex.models import Citation, Claim
from fex.tools import ALL_TOOLS
from fex.verifier import SessionEvidence, verify

STANDARDS = Standards.load()


def _session_producer() -> str:
    profiles = ProducerProfiles.load()._profiles
    return next(pid for pid, p in profiles.items() if p["region"] == "Cauca")


def _respond_state(evidence: SessionEvidence) -> dict:
    return {"producer_id": _session_producer(), "tags": ["water"], "summary_original": "Rain fell.",
            "clause_retriever": FakeRetriever(["APS 3.6.1"]), "evidence": evidence}


def _claim(item: dict, clause: str) -> Claim:
    return Claim(text=item["text"], citation=Citation(source=item["source"], standard_clause=clause,
                                                      period=item["period"], strength=item["strength"]))


def _run_all(evidence: SessionEvidence) -> dict[str, list[dict]]:
    state = _respond_state(evidence)
    return {t.tool_name: call_tool(t, {}, state)[1] for t in ALL_TOOLS}


def test_claims_built_from_tool_items_pass_the_verifier():
    evidence = SessionEvidence()
    results = _run_all(evidence)
    regional, peers, clauses = (results["get_regional_context"], results["find_peer_examples"],
                                results["find_standards"])
    assert regional and peers and [c["source"] for c in clauses] == ["APS 3.6.1"]
    clause = clauses[0]["data"]["clause_id"]
    result = verify([_claim(i, clause) for i in regional], [_claim(p, clause) for p in peers], evidence, STANDARDS)
    assert result.ok, result.problems


def test_every_item_reaches_the_session_evidence_with_its_kind():
    evidence = SessionEvidence()
    results = _run_all(evidence)
    for items in results.values():
        for item in items:
            assert evidence.kind_of(item["source"]) == item["kind"]
    assert evidence.clauses == {"APS 3.6.1"}


def test_a_source_or_clause_no_tool_returned_is_caught():
    evidence = SessionEvidence()
    results = _run_all(evidence)
    invented = Claim(text="Made up", citation=Citation(source="CHIRPS v2.0 rainfall (invented)",
                                                       standard_clause="APS 3.6.1"))
    unretrieved = _claim(results["get_regional_context"][0], "APS 1.1")
    problems = verify([invented, unretrieved], [], evidence, STANDARDS).problems
    assert [(p.index, p.code) for p in problems] == [(0, "unknown_source"), (1, "clause_not_retrieved")]
