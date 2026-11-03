"""Tests for the regional-context (climate) tool."""

from __future__ import annotations

from regional_context.tool import get_regional_climate


def test_exact_region_match_returns_claims(climate_table):
    r = get_regional_climate("Colombia", "Cauca", "Coffee", table_path=climate_table)
    assert r.matched is True
    assert r.match_level == "country_region_crop"
    assert len(r.claims) == 1
    assert r.claims[0].metric == "rainfall_anomaly_pct"


def test_case_and_whitespace_insensitive(climate_table):
    r = get_regional_climate("  COLOMBIA ", "cauca", table_path=climate_table)
    assert r.matched is True
    assert r.match_level == "country_region"


def test_every_claim_has_a_citation(climate_table):
    # Grounding requirement: 100% of claims carry a source citation.
    r = get_regional_climate("Colombia", "Huila", "Coffee", table_path=climate_table)
    assert r.claims
    for claim in r.claims:
        assert claim.citation is not None
        assert claim.citation.source
        assert claim.citation.retrieved


def test_unknown_region_falls_back_to_country(climate_table):
    r = get_regional_climate("Colombia", "Narino", "Coffee", table_path=climate_table)
    assert r.matched is True
    assert r.match_level == "country"
    assert r.note and "No exact match" in r.note


def test_unknown_country_returns_nothing_invented(climate_table):
    # Scope: a location with no pre-loaded data must not fabricate claims.
    r = get_regional_climate("Vietnam", "Khanh Hoa", "Seafood", table_path=climate_table)
    assert r.matched is False
    assert r.claims == []
    assert r.note


def test_missing_table_is_handled(tmp_path):
    missing = str(tmp_path / "does_not_exist.json")
    r = get_regional_climate("Colombia", "Cauca", table_path=missing)
    assert r.matched is False
    assert "pre-extracted" in (r.note or "").lower()
