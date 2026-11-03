"""Validates the REAL generated tables in data/ (not fixtures).

These confirm that the files you would commit are present and well-formed. They
are skipped automatically if the tables have not been generated yet.
"""

from __future__ import annotations

import json
import os

import pytest

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_CLIMATE = os.path.join(_DATA, "regional_climate.json")
_PEERS = os.path.join(_DATA, "peer_projects.json")


@pytest.mark.skipif(not os.path.exists(_CLIMATE), reason="climate table not generated")
def test_real_climate_table_wellformed():
    table = json.load(open(_CLIMATE, encoding="utf-8"))
    assert table["schema_version"] == 1
    assert table["regions"], "expected at least one region"
    for rec in table["regions"]:
        assert rec["country"] and rec["region"]
        for claim in rec["claims"]:
            # grounding: every claim carries a citation with a source
            assert claim["citation"]["source"]


@pytest.mark.skipif(not os.path.exists(_PEERS), reason="peer table not generated")
def test_real_peer_table_wellformed():
    table = json.load(open(_PEERS, encoding="utf-8"))
    assert table["schema_version"] == 1
    assert table["projects"], "expected at least one project"
    for p in table["projects"]:
        assert p["challenge_tag"]
        assert p["project_ref"].startswith("PROJ-")
        assert p["org_ref"].startswith("ORG-")


@pytest.mark.skipif(not os.path.exists(_PEERS), reason="peer table not generated")
def test_real_peer_table_tags_are_in_the_sample_set():
    from peer_examples.schemas import CHALLENGE_TAGS

    table = json.load(open(_PEERS, encoding="utf-8"))
    for p in table["projects"]:
        assert p["challenge_tag"] in CHALLENGE_TAGS
