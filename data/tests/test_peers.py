"""Peer projects and producer profiles built from the FTUSA sample (#16)."""
import csv
import json

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


def test_every_project_has_a_known_tag_status_and_source():
    for p in build_peers()["projects"]:
        assert p["challenge_tag"] in CHALLENGE_TAGS
        assert p["status"] in {"Completed", "In Progress", "In Planning"}
        assert p["source"].endswith(p["project_ref"])


def test_peer_file_holds_no_account_ids():
    text = PEERS_PATH.read_text(encoding="utf-8")
    assert not any(account in text for account in _account_ids())


def test_peer_file_holds_no_known_organization_or_person_names():
    text = PEERS_PATH.read_text(encoding="utf-8")
    for name, _ in NAME_REPLACEMENTS:
        assert name not in text, name


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
