"""Tests for the peer-example tool, including the scope-enforcement negative test."""

from __future__ import annotations

from peer_examples.tool import get_peer_examples


def test_matches_on_challenge_tag(peer_table):
    r = get_peer_examples("water", table_path=peer_table)
    assert r.matched is True
    # 3 water projects exist in the fixture (AAA, BBB, CCC).
    assert len(r.examples) == 3


def test_scope_excludes_session_producers_own_project(peer_table):
    # NEGATIVE TEST: a producer must never be shown their own project as a peer.
    r = get_peer_examples(
        "water", exclude_account_sk="ACCT_SELF", table_path=peer_table
    )
    refs = {e.citation.project_ref for e in r.examples}
    assert "PROJ-AAA" not in refs  # own project excluded
    assert "PROJ-BBB" in refs      # peers still present


def test_crop_and_entity_raise_match_score(peer_table):
    # A 1st Grade Coffee producer should rank the exact crop+entity peer highest.
    r = get_peer_examples(
        "water", crop="Coffee", entity_type="1st Grade",
        exclude_account_sk="ACCT_SELF", table_path=peer_table,
    )
    top = r.examples[0]
    assert top.citation.project_ref == "PROJ-BBB"  # Coffee + 1st Grade
    assert top.match_score == 1.0


def test_multi_crop_field_matches(peer_table):
    # 'Cocoa;Coffee' project should count as a Coffee match.
    r = get_peer_examples(
        "water", crop="Coffee", exclude_account_sk="ACCT_SELF", table_path=peer_table
    )
    ccc = [e for e in r.examples if e.citation.project_ref == "PROJ-CCC"]
    assert ccc and ccc[0].match_score >= 0.8  # tag + crop matched


def test_every_example_has_action_outcome_and_citation(peer_table):
    r = get_peer_examples("water", table_path=peer_table)
    for e in r.examples:
        assert e.action and e.intended_outcome
        assert e.citation.project_ref.startswith("PROJ-")
        assert e.citation.org_ref.startswith("ORG-")


def test_limit_is_respected(peer_table):
    r = get_peer_examples("water", limit=1, table_path=peer_table)
    assert len(r.examples) == 1


def test_no_peers_for_unmatched_tag(peer_table):
    r = get_peer_examples("labor and migration", table_path=peer_table)
    assert r.matched is False
    assert r.examples == []
    assert r.note


def test_citation_never_exposes_real_account_sk(peer_table):
    # The real account id must not leak into the producer-facing citation.
    r = get_peer_examples("water", table_path=peer_table)
    for e in r.examples:
        dumped = e.model_dump()
        assert "ACCT_" not in str(dumped)
