"""Peer-example tool (#16), called through Strands so the session context is injected for real."""
import json

import pytest
from fx_data.peers import PEERS_PATH, PUBLISHABLE, PeerProjects, ProducerProfiles, owner_key

from fex.tools import peer_examples
from fex.tools.peer_examples import find_peer_examples
from tests.tool_harness import call_tool


def _project(catalog_id, org, owner, tags=("water",), crop="Coffee", entity="Cooperative", year=2022):
    return {"catalog_id": catalog_id, "organization": org, "owner_key": owner_key(owner), "tags": list(tags),
            "country": "Peru", "crop": crop, "entity_type": entity, "category": "Environmental",
            "sub_category": "Clean Water", "start_year": year, "description": f"Project {catalog_id}."}


FIXTURE_PROJECTS = [
    _project("P-OWN", "Ceiba Producers' Group", "COFFEE-COOP"),
    _project("P-COFFEE-COOP", "Nogal Producers' Group", "A"),
    _project("P-COFFEE-ESTATE", "Cedro Producers' Group", "B", entity="Estate", year=2024),
    _project("P-BANANA-COOP", "Laurel Producers' Group", "C", crop="Bananas", year=2020),
    _project("P-BANANA-ESTATE", "Roble Producers' Group", "D", crop="Bananas", entity="Estate"),
    _project("P-COCOA-SMALL", "Sauce Producers' Group", "E", crop="Cocoa", entity="Independent Smallholder", year=2025),
    _project("P-SOIL", "Olivo Producers' Group", "F", tags=("soil and land",)),
]
FIXTURE_PROFILES = {
    "COFFEE-COOP": {"country": "Peru", "region": "Junin", "crop": "Coffee", "entity_type": "Cooperative"},
    "BANANA-ESTATE": {"country": "Ecuador", "region": "El Oro", "crop": "Bananas", "entity_type": "Estate"},
}


@pytest.fixture(autouse=True)
def fixture_tables(monkeypatch):
    tables = (PeerProjects({"projects": FIXTURE_PROJECTS}), ProducerProfiles({"profiles": FIXTURE_PROFILES}))
    monkeypatch.setattr(peer_examples, "_tables", lambda: tables)


def _call(pid, tags=("water",), entity_type=None, tool_input=None):
    state = {"producer_id": pid, "tags": list(tags)} | ({"entity_type": entity_type} if entity_type else {})
    status, items = call_tool(find_peer_examples, tool_input or {}, state)
    assert status == "success"
    return items


def _ids(items):
    return [i["source"].rsplit("[", 1)[1].rstrip("]") for i in items]


def test_model_cannot_set_any_parameter():
    assert find_peer_examples.tool_spec["inputSchema"]["json"]["properties"] == {}


def test_never_returns_the_session_producers_own_projects():
    assert "P-OWN" not in _ids(_call("COFFEE-COOP"))


def test_ranking_strength_labels_and_limit():
    # Same crop and entity type, then one of them (most recent first), and at most 3: the two
    # tag-only projects, including the newest one, are cut.
    items = _call("COFFEE-COOP")
    assert _ids(items) == ["P-COFFEE-COOP", "P-COFFEE-ESTATE", "P-BANANA-COOP"]
    assert [i["strength"] for i in items] == ["exact", "nearest", "nearest"]


def test_tag_only_matches_are_limited():
    items = _call("BANANA-ESTATE")
    assert [i["strength"] for i in items] == ["exact", "nearest", "nearest"]
    # As a processor, no project shares the entity type: crop-only matches, then the newest tag-only one.
    items = _call("COFFEE-COOP", entity_type="Processor")
    assert [(i, item["strength"]) for i, item in zip(_ids(items), items)] == [
        ("P-COFFEE-ESTATE", "nearest"), ("P-COFFEE-COOP", "nearest"), ("P-COCOA-SMALL", "limited")]


def test_producers_differing_in_crop_and_entity_type_get_different_examples():
    coffee, banana = _call("COFFEE-COOP"), _call("BANANA-ESTATE")
    assert _ids(coffee)[0] == "P-COFFEE-COOP" and _ids(banana)[0] == "P-BANANA-ESTATE"


def test_a_corrected_entity_type_is_used_for_matching():
    items = _call("COFFEE-COOP", entity_type="Estate")
    assert _ids(items)[0] == "P-COFFEE-ESTATE" and items[0]["strength"] == "exact"


def test_only_confirmed_tags_match_and_no_match_is_an_empty_list():
    assert _ids(_call("COFFEE-COOP", tags=["soil and land"])) == ["P-SOIL"]
    assert _call("COFFEE-COOP", tags=["labor and migration"]) == []


def test_items_hold_only_publishable_fields():
    for item in _call("COFFEE-COOP"):
        assert set(item) == {"source", "kind", "text", "period", "strength", "data"}
        assert item["kind"] == "peer" and set(item["data"]) == set(PUBLISHABLE)
        assert item["source"] == f"Premium project, {item['data']['organization']} [{_ids([item])[0]}]"
        assert "owner_key" not in json.dumps(item)


def test_tags_or_a_producer_id_supplied_by_the_model_are_ignored():
    honest = _call("COFFEE-COOP")
    assert _call("COFFEE-COOP", tool_input={"challenge": "soil and land", "producer_id": "BANANA-ESTATE"}) == honest


def test_no_producer_in_session_is_refused():
    status, text = call_tool(find_peer_examples, {}, {"tags": ["water"]})
    assert status == "error" and "No producer in session" in text


def test_the_real_catalog_returns_no_sample_account_or_project_id(monkeypatch):
    monkeypatch.undo()
    profiles = ProducerProfiles.load()
    raw_ids = set(profiles.ids())
    for pid in profiles.ids()[:20]:
        text = json.dumps(_call(pid, tags=["water", "climate and weather", "biodiversity and conservation"]))
        assert not any(account in text for account in raw_ids)
    assert "account_sk" not in PEERS_PATH.read_text(encoding="utf-8")
