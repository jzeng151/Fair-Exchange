"""Peer-example tool (#16), called through Strands so the session context is injected for real.

The confirmed tags come from the conversation state (data tool contract, #17), never from the model."""
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


def state(pid: str, *tags: str, **extra) -> dict:
    return {"producer_id": pid, "tags": list(tags), **extra}


def test_model_cannot_set_any_parameter():
    assert find_peer_examples.tool_spec["inputSchema"]["json"]["properties"] == {}


def test_never_returns_the_session_producers_own_projects():
    pid = _producer_with_projects("water", "coffee")
    assert _own_refs(pid), "test needs a producer with their own water project"
    status, results = call_tool(find_peer_examples, {}, state(pid, "water"))
    assert status == "success" and results
    assert not {r["data"]["project_ref"] for r in results} & _own_refs(pid)


def test_a_producer_id_or_challenge_supplied_by_the_model_is_ignored():
    pid = _producer_with_projects("water", "coffee")
    other = next(p for p in PROFILES._profiles if p != pid)
    _, honest = call_tool(find_peer_examples, {}, state(pid, "water"))
    _, spoofed = call_tool(find_peer_examples, {"challenge": "health", "producer_id": other}, state(pid, "water"))
    assert spoofed == honest


def test_no_producer_in_session_is_refused():
    status, text = call_tool(find_peer_examples, {}, {"tags": ["water"]})
    assert status == "error" and "No producer in session" in text


def test_no_confirmed_tags_returns_an_empty_list():
    pid = next(iter(PROFILES._profiles))
    assert call_tool(find_peer_examples, {}, state(pid)) == ("success", [])


def test_items_follow_the_data_tool_contract():
    pid = _producer_with_projects("water", "coffee")
    _, results = call_tool(find_peer_examples, {}, state(pid, "water", "climate and weather"))
    assert 0 < len(results) <= 3
    for r in results:
        assert set(r) == {"source", "kind", "text", "period", "strength", "data"}
        assert r["kind"] == "peer" and r["text"] and r["strength"] in {"exact", "nearest", "limited"}
    assert len({r["data"]["org_ref"] for r in results}) == len(results)


def test_producers_with_different_profiles_get_different_examples():
    coffee = _producer_with_projects("climate and weather", "coffee")
    bananas = next(pid for pid, p in PROFILES._profiles.items()
                   if "banana" in (p["crop"] or "").lower())
    _, a = call_tool(find_peer_examples, {}, state(coffee, "climate and weather"))
    _, b = call_tool(find_peer_examples, {}, state(bananas, "climate and weather"))
    assert [r["data"]["project_ref"] for r in a] != [r["data"]["project_ref"] for r in b]
    assert any("coffee" in (r["data"]["crop"] or "").lower() for r in a)
    assert any("banana" in (r["data"]["crop"] or "").lower() for r in b)


def test_results_carry_a_citable_source_and_no_private_identifiers():
    pid = _producer_with_projects("water", "coffee")
    _, results = call_tool(find_peer_examples, {}, state(pid, "water"))
    text = json.dumps(results)
    for r in results:
        assert r["source"].startswith("FTUSA Premium project (sample data, fictionalized) PROJ-")
        assert "owner_key" not in r["data"]
    assert not any(account in text for account in PROFILES._profiles)


def test_at_most_one_example_per_organization():
    pid = next(iter(PROFILES._profiles))
    for tag in ("water", "climate and weather", "biodiversity and conservation"):
        _, results = call_tool(find_peer_examples, {}, state(pid, tag))
        orgs = [r["data"]["org_ref"] for r in results]
        assert len(orgs) == len(set(orgs))


def test_challenge_with_no_peer_projects_returns_an_empty_list():
    # The sample has environmental projects only, so a labor challenge has no precedent.
    pid = next(iter(PROFILES._profiles))
    status, results = call_tool(find_peer_examples, {}, state(pid, "labor and migration"))
    assert status == "success" and results == []


@pytest.mark.parametrize("tag", ["water", "climate and weather"])
def test_ranking_prefers_same_crop(tag):
    pid = _producer_with_projects(tag, "coffee")
    profile = PROFILES.get(pid)
    top = PeerProjects.load().find(tag, profile, limit=1)[0]
    assert "coffee" in (top["crop"] or "").lower()
