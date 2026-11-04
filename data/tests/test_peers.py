"""Peer projects and producer profiles built from the FTUSA sample (#16)."""
import csv
import json
import re

from fx_data.peers import (ACCOUNTS_CSV, FICTIONAL_NAMES, NAME_REPLACEMENTS, PEERS_PATH, PROFILES_PATH,
                           PROJECTS_CSV, PUBLISHABLE, PeerProjects, build_peers, build_profiles,
                           build_status_index, fictionalize, owner_key, resolve_status, tag_for)

CHALLENGE_TAGS = {
    "climate and weather", "water", "soil and land", "market and price", "labor and migration",
    "financial and access to capital", "education", "health", "infrastructure",
    "biodiversity and conservation", "social and community",
}


def _account_ids() -> set[str]:
    with open(ACCOUNTS_CSV, encoding="utf-8") as fh:
        return {r["account_sk"] for r in csv.DictReader(fh)}


def test_committed_tables_match_the_sample_data():
    assert json.loads(PEERS_PATH.read_text(encoding="utf-8")) == build_peers()
    assert json.loads(PROFILES_PATH.read_text(encoding="utf-8")) == build_profiles()


def test_every_project_is_kept_except_placeholders():
    with open(PROJECTS_CSV, encoding="utf-8") as fh:
        total = sum(1 for _ in csv.DictReader(fh))
    peers = build_peers()
    assert len(peers["projects"]) + peers["dropped_placeholder_rows"] == total
    assert not any("lorem" in json.dumps(p).lower() for p in peers["projects"])


def test_catalog_rows_hold_only_publishable_fields_plus_id_tags_and_owner_key():
    for p in build_peers()["projects"]:
        assert set(p) == set(PUBLISHABLE) | {"catalog_id", "tags", "owner_key"}
        assert p["tags"] and set(p["tags"]) <= CHALLENGE_TAGS
        assert p["start_year"] is None or 2000 <= p["start_year"] <= 2030


def test_start_year_is_resolved_for_almost_every_project():
    projects = build_peers()["projects"]
    assert sum(p["start_year"] is None for p in projects) <= 12, "the status join has stopped resolving"


def test_catalog_ids_are_unique_so_a_citation_names_one_project():
    ids = [p["catalog_id"] for p in build_peers()["projects"]]
    assert len(ids) == len(set(ids))


def test_organizations_are_fictional_and_one_name_per_organization():
    projects = build_peers()["projects"]
    assert {p["organization"] for p in projects} <= set(FICTIONAL_NAMES)
    by_owner = {}
    for p in projects:
        assert by_owner.setdefault(p["owner_key"], p["organization"]) == p["organization"]
    assert len(set(by_owner.values())) == len(by_owner)


def test_a_project_never_borrows_another_projects_status():
    # One account has three projects with the same description and different years and statuses.
    index = build_status_index()
    with open(PROJECTS_CSV, encoding="utf-8") as fh:
        rows = {r["translated_project_name"]: r for r in csv.DictReader(fh)}
    first = resolve_status(index, rows["21. Reforestation of Green Areas"])
    assert (first["project_status_name"], first["project_start_date"]) == ("Completed", "2021-01-01")
    assert resolve_status(index, rows["23. Reforestation of green areas"])["project_start_date"] == "2023-01-01"


# --- find (#16 lookup) -------------------------------------------------------------------------

def _row(catalog_id, org, owner, tags=("water",), crop="Coffee", entity="Cooperative", year=2020):
    return {"catalog_id": catalog_id, "organization": org, "owner_key": owner_key(owner), "tags": list(tags),
            "country": "Peru", "crop": crop, "entity_type": entity, "category": "Environmental",
            "sub_category": "Clean Water", "start_year": year, "description": f"Project {catalog_id}."}


def _catalog(*rows):
    return PeerProjects({"projects": list(rows)})


def test_find_leaves_out_the_producers_own_projects_and_other_tags():
    catalog = _catalog(_row("P1", "Ceiba Producers' Group", "ME"), _row("P2", "Nogal Producers' Group", "OTHER"),
                       _row("P3", "Cedro Producers' Group", "OTHER2", tags=("soil and land",)))
    items = catalog.find("ME", {"water"}, {"coffee"}, "Cooperative")
    assert [i["data"]["description"] for i in items] == ["Project P2."]


def test_find_strength_follows_crop_and_entity_type_and_ranks_strongest_first():
    catalog = _catalog(_row("P1", "A", "a", crop="Cocoa", entity="Estate"),
                       _row("P2", "B", "b", crop="Coffee", entity="Estate"),
                       _row("P3", "C", "c"))
    items = catalog.find("ME", {"water"}, {"coffee"}, "Cooperative")
    assert [i["strength"] for i in items] == ["exact", "nearest", "limited"]
    assert [i["source"] for i in items] == ["Premium project, C [P3]", "Premium project, B [P2]",
                                            "Premium project, A [P1]"]


def test_find_breaks_ties_by_most_recent_and_keeps_one_project_per_organization():
    catalog = _catalog(_row("P1", "A", "a", year=2019), _row("P2", "A", "a", year=2023),
                       _row("P3", "B", "b", year=2021), _row("P4", "C", "c", year=2018), _row("P5", "D", "d"))
    items = catalog.find("ME", {"water"}, {"coffee"}, "Cooperative")
    assert [i["source"] for i in items] == ["Premium project, A [P2]", "Premium project, B [P3]",
                                            "Premium project, D [P5]"]


def test_find_returns_only_publishable_fields_and_nothing_when_no_tag_matches():
    catalog = _catalog(_row("P1", "A", "a"))
    (item,) = catalog.find("ME", {"water"}, set(), None)
    assert set(item) == {"source", "kind", "text", "period", "strength", "data"}
    assert set(item["data"]) == set(PUBLISHABLE) and item["kind"] == "peer"
    assert catalog.find("ME", {"education"}, {"coffee"}, "Cooperative") == []


def test_peer_file_holds_no_account_ids():
    text = PEERS_PATH.read_text(encoding="utf-8")
    assert not any(account in text for account in _account_ids())


def _contains(text: str, name: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.IGNORECASE))


def test_peer_file_holds_no_known_organization_or_person_names():
    text = PEERS_PATH.read_text(encoding="utf-8")
    for name, _ in NAME_REPLACEMENTS:
        assert not _contains(text, name), name


def test_names_found_in_code_review_are_gone_in_any_spelling():
    text = PEERS_PATH.read_text(encoding="utf-8")
    for name in ("CAFESCOR", "Coopervitae", "MELCOOP", "Nobland", "Chemase", "Kitumbe", "Finteaflo",
                 "Rahmat", "Joan Fernie", "FABICOOP", "Asoprokia", "CAFISEVILLA", "COMIXCAEL",
                 "Montesol", "Campo Limpio", "Zarzamora"):
        assert not _contains(text, name), name


def test_names_are_replaced_whatever_their_capitalization():
    assert fictionalize("Latrine project for CAFESCOR members and Cafescor staff") == \
        "Latrine project for the cooperative members and the cooperative staff"
    assert fictionalize("Safescorporation") == "Safescorporation"  # whole names only


def test_fictionalize_replaces_longest_name_first():
    assert fictionalize("SCPP Barra de Palmitas and SCPP") == "the fishing cooperative and fishing cooperative"


def test_owner_key_is_stable_and_does_not_reveal_the_account():
    assert owner_key("ABC") == owner_key("ABC") != owner_key("ABD")
    assert "ABC" not in owner_key("ABC")


def test_subcategory_decides_the_tag_then_keywords():
    assert tag_for("Clean Water") == "water"
    assert tag_for("", "Solar panels for the pump") == "climate and weather"
    assert tag_for("", "Composting to reduce soil erosion") == "soil and land"
    assert tag_for("", "Community clean-up day") == "biodiversity and conservation"


def test_every_sample_producer_has_a_profile():
    profiles = build_profiles()["profiles"]
    assert set(profiles) == _account_ids()
    assert all(p["country"] for p in profiles.values())
