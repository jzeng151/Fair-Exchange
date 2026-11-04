"""Peer-example tool (#16), called through Strands so the session context is injected for real."""
import json

import pytest
from fx_data.peers import PEERS_PATH, PeerProjects, ProducerProfiles, owner_key
from tests.tool_harness import call_tool

from fex.tools.peer_examples import find_peer_examples

PROFILES = ProducerProfiles.load()
PEER_ROWS = json.loads(PEERS_PATH.read_text(encoding="utf-8"))["projects"]


def _producer_with_projects(tag: str, crop_word: str) -> str:
    """A real sample producer who has their own project for `tag` and grows `crop_word`."""
    for row in PEER_ROWS:
        if row["challenge_tag"] != tag:
            continue
        for pid, profile in PROFILES._profiles.items():
            if owner_key(pid) == row["owner_key"] and crop_word in (profile["crop"] or "").lower():
                return pid
    raise AssertionError(f"no sample producer with a {tag} project growing {crop_word}")


def _own_refs(pid: str) -> set[str]:
    return {r["project_ref"] for r in PEER_ROWS if r["owner_key"] == owner_key(pid)}


def test_model_can_only_set_the_challenge():
    assert list(find_peer_examples.tool_spec["inputSchema"]["json"]["properties"]) == ["challenge"]


def test_never_returns_the_session_producers_own_projects():
    pid = _producer_with_projects("water", "coffee")
    assert _own_refs(pid), "test needs a producer with their own water project"
    status, results = call_tool(find_peer_examples, {"challenge": "water"}, {"producer_id": pid})
    assert status == "success" and results
    assert not {r["project_ref"] for r in results} & _own_refs(pid)


def test_a_producer_id_supplied_by_the_model_is_ignored():
    pid = _producer_with_projects("water", "coffee")
    other = next(p for p in PROFILES._profiles if p != pid)
    _, honest = call_tool(find_peer_examples, {"challenge": "water"}, {"producer_id": pid})
    _, spoofed = call_tool(find_peer_examples, {"challenge": "water", "producer_id": other},
                           {"producer_id": pid})
    assert spoofed == honest


def test_no_producer_in_session_is_refused():
    status, text = call_tool(find_peer_examples, {"challenge": "water"}, {})
    assert status == "error" and "No producer in session" in text


def test_unknown_challenge_tag_is_rejected():
    pid = next(iter(PROFILES._profiles))
    status, _ = call_tool(find_peer_examples, {"challenge": "drought"}, {"producer_id": pid})
    assert status == "error"


def test_producers_with_different_profiles_get_different_examples():
    coffee = _producer_with_projects("climate and weather", "coffee")
    bananas = next(pid for pid, p in PROFILES._profiles.items()
                   if "banana" in (p["crop"] or "").lower())
    _, a = call_tool(find_peer_examples, {"challenge": "climate and weather"}, {"producer_id": coffee})
    _, b = call_tool(find_peer_examples, {"challenge": "climate and weather"}, {"producer_id": bananas})
    assert [r["project_ref"] for r in a] != [r["project_ref"] for r in b]
    assert any("coffee" in (r["crop"] or "").lower() for r in a)
    assert any("banana" in (r["crop"] or "").lower() for r in b)


def test_results_carry_a_citable_source_and_no_private_identifiers():
    pid = _producer_with_projects("water", "coffee")
    _, results = call_tool(find_peer_examples, {"challenge": "water"}, {"producer_id": pid})
    text = json.dumps(results)
    for r in results:
        assert r["source"].startswith("FTUSA Premium project (sample data, fictionalized) PROJ-")
        assert "owner_key" not in r
    assert not any(account in text for account in PROFILES._profiles)


def test_at_most_one_example_per_organization():
    pid = next(iter(PROFILES._profiles))
    for tag in ("water", "climate and weather", "biodiversity and conservation"):
        _, results = call_tool(find_peer_examples, {"challenge": tag}, {"producer_id": pid})
        orgs = [r["org_ref"] for r in results]
        assert len(orgs) == len(set(orgs))


def test_challenge_with_no_peer_projects_returns_an_empty_list():
    # The sample has environmental projects only, so a labor challenge has no precedent.
    pid = next(iter(PROFILES._profiles))
    status, results = call_tool(find_peer_examples, {"challenge": "labor and migration"},
                                {"producer_id": pid})
    assert status == "success" and results == []


@pytest.mark.parametrize("tag", ["water", "climate and weather"])
def test_ranking_prefers_same_crop(tag):
    pid = _producer_with_projects(tag, "coffee")
    profile = PROFILES.get(pid)
    top = PeerProjects.load().find(tag, profile, limit=1)[0]
    assert "coffee" in (top["crop"] or "").lower()
