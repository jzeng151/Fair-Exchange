"""Seam 3 (#17): after deploy, a known challenge returns at least one clause from the real Knowledge Base.

Runs only against a deployed KB: infra/deploy.sh sets FEX_STANDARDS_KB_ID and runs it.
Elsewhere (CI, local unit runs) it is skipped.
"""
import os

import pytest
from fx_data.standards import Standards

from fex.tools.standards import KB_ID_ENV, TOP_K, BedrockKbRetriever, standards_query

pytestmark = pytest.mark.skipif(not os.environ.get(KB_ID_ENV), reason=f"{KB_ID_ENV} not set (no deployed KB)")


def test_a_known_challenge_returns_real_clauses():
    query = standards_query({
        "summary_english": "Rainfall has dropped for two seasons and the coffee harvest fell; the cooperative is "
                           "worried about water for processing.",
        "tags": ["water", "climate and weather"],
    })
    clauses = BedrockKbRetriever(os.environ[KB_ID_ENV]).retrieve(query, TOP_K)
    assert clauses, "the Knowledge Base returned no clauses: was ingestion run?"
    standards = Standards.load()
    assert all(standards.exists(c.clause_id) for c in clauses), [c.clause_id for c in clauses]
    assert len({c.clause_id for c in clauses}) == len(clauses)
