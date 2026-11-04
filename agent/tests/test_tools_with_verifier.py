"""Tool results feed the citation verifier (#17) the way docs/handoff/tool-contracts.md says."""
from fx_data.peers import ProducerProfiles
from fx_data.standards import Standards
from tests.tool_harness import call_tool

from fex.models import Citation, Claim
from fex.tools.peer_examples import find_peer_examples
from fex.tools.producer_record import get_producer_record
from fex.tools.regional_context import get_regional_context
from fex.verifier import SessionEvidence, verify

STANDARDS = Standards.load()
CLAUSE = "APS 1.1"  # any real clause; choosing the right one is check_standards' job


def _session_producer() -> str:
    profiles = ProducerProfiles.load()._profiles
    return next(pid for pid, p in profiles.items() if p["region"] == "Cauca")


STATE = {"tags": ["water", "climate and weather"]}


def _claim(item: dict) -> Claim:
    return Claim(text=item["text"], citation=Citation(source=item["source"], standard_clause=CLAUSE,
                                                      period=item["period"], strength=item["strength"]))


def test_claims_built_from_tool_results_pass_the_verifier():
    state = {"producer_id": _session_producer(), **STATE}
    _, record = call_tool(get_producer_record, {}, state)
    _, regional = call_tool(get_regional_context, {}, state)
    _, peers = call_tool(find_peer_examples, {}, state)
    assert record and regional and peers

    evidence = SessionEvidence()
    for items in (record, regional, peers):
        evidence.record_tool_result(items)

    result = verify([_claim(i) for i in record + regional], [_claim(p) for p in peers], evidence, STANDARDS)
    assert result.ok, result.problems


def test_a_source_no_tool_returned_is_caught():
    evidence = SessionEvidence()
    _, peers = call_tool(find_peer_examples, {}, {"producer_id": _session_producer(), **STATE})
    evidence.record_tool_result(peers)
    invented = Claim(text="Made up", citation=Citation(source="CHIRPS v2.0 rainfall (invented)",
                                                       standard_clause=CLAUSE))
    assert not verify([invented], [], evidence, STANDARDS).ok
