"""Peer projects and producer profiles built from the FTUSA sample (#16)."""
import csv
import json
import re

from fx_data.peers import (ACCOUNTS_CSV, NAME_REPLACEMENTS, PEERS_PATH, PROFILES_PATH, PROJECTS_CSV,
                           build_peers, build_profiles, fictionalize, owner_key, tag_for)

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


def test_every_project_has_a_known_tag_and_source():
    for p in build_peers()["projects"]:
        assert p["challenge_tag"] in CHALLENGE_TAGS
        assert p["source"].endswith(p["project_ref"])


def test_status_is_a_known_value_or_missing_together_with_its_dates():
    projects = build_peers()["projects"]
    for p in projects:
        if p["status"] is None:
            assert p["start_date"] is None and p["end_date"] is None
        else:
            assert p["status"] in {"Completed", "In Progress", "In Planning"}
    assert sum(p["status"] is None for p in projects) <= 12, "the join has stopped resolving projects"


def test_project_refs_are_unique_so_a_citation_names_one_project():
    refs = [p["project_ref"] for p in build_peers()["projects"]]
    assert len(refs) == len(set(refs))


def test_a_project_never_borrows_another_projects_status():
    # One account has three projects with the same description and different years and statuses.
    by_name = {p["name"]: p for p in build_peers()["projects"]}
    assert (by_name["21. Reforestation of Green Areas"]["status"],
            by_name["21. Reforestation of Green Areas"]["start_date"]) == ("Completed", "2021-01-01")
    assert by_name["23. Reforestation of green areas"]["start_date"] == "2023-01-01"
    # Identical repeats whose statuses disagree get no status at all.
    unresolved = [p for p in build_peers()["projects"] if p["status"] is None]
    assert unresolved, "expected the sample's genuinely ambiguous projects to be left without a status"


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
