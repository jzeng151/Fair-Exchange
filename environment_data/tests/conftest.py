"""Shared pytest fixtures: tiny, deterministic tables for the two tools.

Tests run against these fixtures (not the live 349-row data) so they are fast and
deterministic. A separate test module checks that the REAL generated tables exist
and are well-formed.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def climate_table(tmp_path):
    """A minimal regional-climate table written to a temp file; returns its path."""
    table = {
        "schema_version": 1,
        "generated": "2026-01-01T00:00:00Z",
        "description": "test fixture",
        "regions": [
            {
                "country": "colombia",
                "region": "cauca",
                "centroid": {"lat": 2.44, "lon": -76.61},
                "claims": [
                    {
                        "statement": "Rainfall 10% below the 10-year average.",
                        "metric": "rainfall_anomaly_pct",
                        "value": -10.0,
                        "unit": "percent",
                        "citation": {
                            "source": "CHIRPS",
                            "detail": "test",
                            "retrieved": "2026-01-01",
                            "url": "https://example.org/chirps",
                        },
                    }
                ],
            },
            {
                "country": "colombia",
                "region": "huila",
                "centroid": {"lat": 2.54, "lon": -75.53},
                "claims": [
                    {
                        "statement": "Baseline water stress is Low.",
                        "metric": "baseline_water_stress",
                        "value": 0.5,
                        "unit": "category",
                        "citation": {
                            "source": "Aqueduct 4.0",
                            "detail": "test",
                            "retrieved": "2026-01-01",
                            "url": "https://example.org/aqueduct",
                        },
                    }
                ],
            },
        ],
    }
    path = tmp_path / "regional_climate.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return str(path)


@pytest.fixture
def peer_table(tmp_path):
    """A minimal peer-projects table written to a temp file; returns its path."""
    table = {
        "schema_version": 1,
        "generated": "2026-01-01T00:00:00Z",
        "description": "test fixture",
        "projects": [
            {
                "project_ref": "PROJ-AAA",
                "org_ref": "ORG-AAA",
                "_account_sk": "ACCT_SELF",
                "challenge_tag": "water",
                "crop": "Coffee",
                "country": "Colombia",
                "region": "Cauca",
                "entity_type": "1st Grade",
                "subcategory": "Clean Water",
                "name": "Own water project",
                "challenge": "Water pollution from processing.",
                "action": "Built honey-water treatment wells.",
                "intended_outcome": "Reduce water pollution.",
            },
            {
                "project_ref": "PROJ-BBB",
                "org_ref": "ORG-BBB",
                "_account_sk": "ACCT_PEER1",
                "challenge_tag": "water",
                "crop": "Coffee",
                "country": "Peru",
                "region": "San Martin",
                "entity_type": "1st Grade",
                "subcategory": "Clean Water",
                "name": "Peer water project",
                "challenge": "Honey water pollution.",
                "action": "Installed vetiver seedbeds and wells.",
                "intended_outcome": "Treat honey water.",
            },
            {
                "project_ref": "PROJ-CCC",
                "org_ref": "ORG-CCC",
                "_account_sk": "ACCT_PEER2",
                "challenge_tag": "water",
                "crop": "Cocoa;Coffee",
                "country": "Brazil",
                "region": "Sao Paulo",
                "entity_type": "Estate",
                "subcategory": "Clean Water",
                "name": "Peer multi-crop project",
                "challenge": "Water management.",
                "action": "Reforestation for water preservation.",
                "intended_outcome": "Water preservation.",
            },
            {
                "project_ref": "PROJ-DDD",
                "org_ref": "ORG-DDD",
                "_account_sk": "ACCT_PEER3",
                "challenge_tag": "climate and weather",
                "crop": "Coffee",
                "country": "Honduras",
                "region": "Copan",
                "entity_type": "1st Grade",
                "subcategory": "Climate Change Mitigation/Adaptation (Clean Energy, Agroforestry etc.)",
                "name": "Peer climate project",
                "challenge": "Rising temperatures.",
                "action": "Planted shade trees (agroforestry).",
                "intended_outcome": "Cooler microclimate.",
            },
        ],
    }
    path = tmp_path / "peer_projects.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return str(path)
