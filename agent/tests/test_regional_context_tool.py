"""Regional-context tool (#15), called through Strands so the session context is injected for real."""
from fx_data.peers import ProducerProfiles
from fx_data.regional import RegionalFacts, normalize
from tests.tool_harness import call_tool

from fex.tools.regional_context import get_regional_context

PROFILES = ProducerProfiles.load()
FACTS = RegionalFacts.load()
COVERED = {(normalize(r["country"]), normalize(r["region"])) for r in FACTS._table["regions"]}


def _producer(country: str, crop_word: str) -> str:
    for pid, p in PROFILES._profiles.items():
        if (normalize(p["country"]) == normalize(country) and crop_word in (p["crop"] or "").lower()
                and (normalize(p["country"]), normalize(p["region"])) in COVERED):
            return pid
    raise AssertionError(f"no covered {crop_word} producer in {country}")


def test_model_cannot_set_any_parameter():
    assert get_regional_context.tool_spec["inputSchema"]["json"]["properties"] == {}


def test_returns_cited_facts_for_the_session_producers_own_region():
    pid = _producer("Colombia", "coffee")
    status, answer = call_tool(get_regional_context, {}, {"producer_id": pid})
    assert status == "success" and answer["matched"] and answer["match_level"] == "region"
    profile = PROFILES.get(pid)
    assert answer["region"]["region"] == profile.region
    sources = {f["source"] for f in answer["facts"]}
    assert any(s.startswith("CHIRPS") for s in sources)
    assert any(s.startswith("WRI Aqueduct") for s in sources)
    assert any(s.startswith("World Bank") for s in sources)
    for fact in answer["facts"]:
        assert fact["text"] and fact["source"] and fact["period"]
        assert fact["strength"] in {"exact", "nearest", "limited"}


def test_a_location_supplied_by_the_model_is_ignored():
    pid = _producer("Colombia", "coffee")
    _, honest = call_tool(get_regional_context, {}, {"producer_id": pid})
    _, spoofed = call_tool(get_regional_context, {"country": "Peru", "region": "Junin"},
                           {"producer_id": pid})
    assert spoofed == honest


def test_different_regions_get_different_facts():
    _, a = call_tool(get_regional_context, {}, {"producer_id": _producer("Colombia", "coffee")})
    _, b = call_tool(get_regional_context, {}, {"producer_id": _producer("Peru", "coffee")})
    assert a["region"] != b["region"]
    assert [f["text"] for f in a["facts"]] != [f["text"] for f in b["facts"]]


def test_unknown_producer_gets_no_facts():
    status, answer = call_tool(get_regional_context, {}, {"producer_id": "NOT-A-PRODUCER"})
    assert status == "success" and answer == {"matched": False, "match_level": "none", "facts": [],
                                              "note": "This producer's location is not on record."}


def test_no_producer_in_session_is_refused():
    status, text = call_tool(get_regional_context, {}, {})
    assert status == "error" and "No producer in session" in text
