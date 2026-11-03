"""Issue #9: APS/FPS clauses loaded from the real workbooks in docs/olena_data/."""
import pytest

from fx_data.standards_loader import build_clauses


@pytest.fixture(scope="module")
def clauses():
    return {c["id"]: c for c in build_clauses()}


def test_aps_farm_size_repeats_merge_into_one_clause(clauses):
    # In the workbook, objective 2.1.1 appears three times: SF, MF and LF
    assert clauses["APS 2.1.1"]["farm_sizes"] == ["SF", "MF", "LF"]


def test_aps_objective_keeps_official_spanish_and_french_text(clauses):
    text = clauses["APS 1.1.1"]["text"]
    assert text["en"].startswith("Objective 1.1.1: The Certificate Holder")
    assert text["es"].startswith("Objetivo 1.1.1: El Titular del Certificado")
    assert text["fr"].startswith("Objectif 1.1.1")


def test_aps_criterion_points_to_its_objective(clauses):
    criterion = clauses["APS 1.1.1.a"]
    assert criterion["level"] == "criterion"
    assert criterion["parent"] == "APS 1.1.1"
    assert criterion["text"]["en"].startswith("The Certificate Holder understands the intent")


def test_amendment_variants_attach_to_the_base_clause(clauses):
    assert "vCNVN" in clauses["APS 1.1.1.a"]["variants"]
    assert not [cid for cid in clauses if "_v" in cid]  # variants are never separate citations


def test_fps_is_the_factory_standard_in_english_only(clauses):
    objective = clauses["FPS 1.1.1"]
    assert objective["text"]["en"].startswith("Objective 1.1.1: The factory")
    assert "es" not in objective["text"]
    assert clauses["FPS 1.1.1.a"]["level"] == "criterion"


def test_fps_sub_module_heading_is_its_own_level(clauses):
    assert clauses["FPS 1.1"]["level"] == "sub-module"


def test_every_clause_has_english_text(clauses):
    missing = [cid for cid, c in clauses.items() if not c["text"].get("en")]
    assert missing == []


def test_aps_sub_module_headings_come_from_the_sub_module_column(clauses):
    heading = clauses["APS 1.1"]
    assert heading["level"] == "sub-module"
    assert heading["text"]["en"].startswith("Sub-Module 1.1: Small Producers and Workers")
    assert heading["text"]["es"].startswith("Submódulo 1.1")


def test_every_parent_reference_points_to_an_existing_clause(clauses):
    orphans = [cid for cid, c in clauses.items() if c["parent"] and c["parent"] not in clauses]
    assert orphans == []
