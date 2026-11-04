"""Tool results feed the citation verifier (#17) the way docs/handoff/tool-contracts.md says."""
from fx_data.peers import ProducerProfiles
from fx_data.standards import Standards
from tests.tool_harness import call_tool

from fex.models import Citation, Claim
from fex.tools.peer_examples import find_peer_examples
from fex.tools.regional_context import get_regional_context
from fex.verifier import SessionEvidence, verify

STANDARDS = Standards.load()
CLAUSE = "APS 1.1"  # any real clause; choosing the right one is check_standards' job


def _session_producer() -> str:
    profiles = ProducerProfiles.load()._profiles
    return next(pid for pid, p in profiles.items() if p["region"] == "Cauca")


def _claim(item: dict) -> Claim:
    text = item.get("text") or item["action"]
    period = item.get("period") or item.get("start_date")
    return Claim(text=text, citation=Citation(source=item["source"], standard_clause=CLAUSE,
                                              period=period, strength=item.get("strength", "exact")))


def test_claims_built_from_tool_results_pass_the_verifier():
    state = {"producer_id": _session_producer()}
    _, regional = call_tool(get_regional_context, {}, state)
    _, peers = call_tool(find_peer_examples, {"challenge": "water"}, state)
    assert regional["facts"] and peers

    evidence = SessionEvidence()
    evidence.record_tool_result(regional["facts"])
    evidence.record_tool_result(peers)

    result = verify([_claim(f) for f in regional["facts"]], [_claim(p) for p in peers], evidence, STANDARDS)
    assert result.ok, result.problems


def test_a_source_no_tool_returned_is_caught():
    evidence = SessionEvidence()
    _, peers = call_tool(find_peer_examples, {"challenge": "water"}, {"producer_id": _session_producer()})
    evidence.record_tool_result(peers)
    invented = Claim(text="Made up", citation=Citation(source="CHIRPS v2.0 rainfall (invented)",
                                                       standard_clause=CLAUSE))
    assert not verify([invented], [], evidence, STANDARDS).ok
