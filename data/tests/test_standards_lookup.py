"""Issue #9: FEX and the citation verifier (#17) look clauses up by ID and by text."""
from pathlib import Path

import pytest

from fx_data.standards import Standards
from fx_data.standards_loader import export_text

CLAUSES_JSON = Path(__file__).resolve().parents[1] / "src" / "fx_data" / "clauses.json"


@pytest.fixture(scope="module")
def standards():
    return Standards.load()


def test_get_accepts_loosely_typed_ids(standards):
    assert standards.get("aps 2.1.1")["id"] == "APS 2.1.1"
    assert standards.get("  FPS   1.1.1.a ")["id"] == "FPS 1.1.1.a"


def test_get_unknown_clause_returns_none(standards):
    assert standards.get("APS 9.9.9") is None


def test_exists_tells_the_verifier_whether_a_citation_is_real(standards):
    assert standards.exists("APS 1.1.1") is True
    assert standards.exists("FPS 1.1") is True
    assert standards.exists("APS 9.9.9") is False
    assert standards.exists("APS 1.1.1.a_vCNVN") is False  # variants are not separate citations
    assert standards.exists("") is False


def test_search_finds_clauses_by_english_text(standards):
    results = standards.search("forced labor")
    assert results, "expected at least one clause about forced labor"
    assert "forced" in results[0]["text"]["en"].lower()


def test_search_finds_clauses_by_spanish_text(standards):
    results = standards.search("trabajo forzoso")
    assert results and "forzoso" in results[0]["text"]["es"].lower()


def test_search_can_be_limited_to_one_standard(standards):
    results = standards.search("premium", standard="FPS", limit=5)
    assert 0 < len(results) <= 5
    assert {r["standard"] for r in results} == {"FPS"}


def test_committed_clauses_json_matches_the_workbooks():
    assert CLAUSES_JSON.read_text(encoding="utf-8") == export_text(), \
        "fx_data/clauses.json is stale; run: PYTHONPATH=src uv run python -m fx_data.standards_loader"


def test_search_matches_whole_words_not_fragments(standards):
    # "agua" (water) must not match "salvaguardas" (safeguards)
    import re
    for clause in standards.search("agua", limit=5):
        assert re.search(r"\bagua", clause["text"].get("es", "").lower()), clause["id"]
