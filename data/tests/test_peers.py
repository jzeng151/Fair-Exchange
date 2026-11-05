"""The peer catalog (#16) as the generator writes it (#7), and the peer lookup."""
import csv
import json
import re

from fx_data.peers import (ACCOUNTS_CSV, FICTIONAL_NAMES, NAME_REPLACEMENTS, PROJECTS_CSV, PUBLISHABLE,
                           PeerProjects, build_status_index, crop_set, fictionalize, resolve_status)
from fx_data.tables import read_table, table_path

CATALOG = read_table("peer_catalog")
CATALOG_TEXT = table_path("peer_catalog").read_text(encoding="utf-8")

CHALLENGE_TAGS = {
    "climate and weather", "water", "soil and land", "market and price", "labor and migration",
    "financial and access to capital", "education", "health", "infrastructure",
    "biodiversity and conservation", "social and community",
}


def _account_ids() -> set[str]:
    with open(ACCOUNTS_CSV, encoding="utf-8") as fh:
        return {r["account_sk"] for r in csv.DictReader(fh)}


def test_catalog_has_no_placeholder_text():
    assert CATALOG and "lorem" not in CATALOG_TEXT.lower()


def test_catalog_rows_hold_only_publishable_fields_plus_id_tags_and_owner():
    for p in CATALOG:
        assert set(p) == set(PUBLISHABLE) | {"catalog_id", "tags", "owner_producer_id"}
        assert p["tags"] and set(p["tags"]) <= CHALLENGE_TAGS
        assert p["start_year"] is None or 2000 <= p["start_year"] <= 2030


def test_start_year_is_resolved_for_almost_every_project():
    assert sum(p["start_year"] is None for p in CATALOG) <= 12, "the status join has stopped resolving"


def test_catalog_ids_are_unique_so_a_citation_names_one_project():
    ids = [p["catalog_id"] for p in CATALOG]
    assert len(ids) == len(set(ids))


def test_organizations_are_fictional_and_one_name_per_organization():
    assert {p["organization"] for p in CATALOG} <= set(FICTIONAL_NAMES)
    by_owner = {}
    for p in CATALOG:
        assert by_owner.setdefault(p["owner_producer_id"], p["organization"]) == p["organization"]
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
    return {"catalog_id": catalog_id, "organization": org, "owner_producer_id": owner, "tags": list(tags),
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


def test_other_never_counts_as_a_match():
    # #14 spec: "other" is never used for matching. Two producers of unknown structure or crop are not alike.
    catalog = _catalog(_row("P1", "A", "a", crop="coffee", entity="other"), _row("P2", "B", "b", crop="other", entity="other"))
    items = catalog.find("ME", {"water"}, {"coffee"}, "other")
    assert [(i["source"], i["strength"]) for i in items] == [("Premium project, A [P1]", "nearest"),
                                                             ("Premium project, B [P2]", "limited")]


def test_other_crop_in_a_profile_is_ignored():
    assert crop_set("coffee;other") == {"coffee"}
    catalog = _catalog(_row("P1", "A", "a", crop="other", entity="smallholder"))
    (item,) = catalog.find("ME", {"water"}, crop_set("other"), "cooperative")
    assert item["strength"] == "limited"


def test_find_returns_only_publishable_fields_and_nothing_when_no_tag_matches():
    catalog = _catalog(_row("P1", "A", "a"))
    (item,) = catalog.find("ME", {"water"}, set(), None)
    assert set(item) == {"source", "kind", "text", "period", "strength", "data"}
    assert set(item["data"]) == set(PUBLISHABLE) and item["kind"] == "peer"
    assert catalog.find("ME", {"education"}, {"coffee"}, "Cooperative") == []


def test_account_ids_appear_only_in_the_private_owner_column():
    # #7 spec: sample account IDs may appear in owner_producer_id, never in a publishable field.
    accounts = _account_ids()
    for p in CATALOG:
        assert p["owner_producer_id"] in accounts or p["owner_producer_id"].startswith("SYN-")
        public = json.dumps({k: v for k, v in p.items() if k != "owner_producer_id"})
        assert not any(account in public for account in accounts)


def _contains(text: str, name: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.IGNORECASE))


def test_peer_file_holds_no_known_organization_or_person_names():
    for name, _ in NAME_REPLACEMENTS:
        assert not _contains(CATALOG_TEXT, name), name


def test_names_found_in_code_review_are_gone_in_any_spelling():
    text = CATALOG_TEXT
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
