"""#101 + #17: a local clause retriever, so the standards tool works with no Knowledge Base (local runs, CI)."""
from fx_data.standards import Standards

from fex.tools.standards import RetrievedClause
from fex.tools.standards_local import LocalClauseRetriever

STANDARDS = Standards.load()


def test_returns_real_clauses_for_a_challenge_query():
    found = LocalClauseRetriever().retrieve("Rainfall dropped and the coffee harvest fell. Challenges: water", 5)
    assert found and len(found) <= 5
    assert all(isinstance(c, RetrievedClause) and STANDARDS.exists(c.clause_id) for c in found)
    assert all(c.text and c.standard in ("APS", "FPS") for c in found)


def test_is_deterministic_and_respects_the_limit():
    r = LocalClauseRetriever()
    a, b = r.retrieve("water irrigation", 3), r.retrieve("water irrigation", 3)
    assert [c.clause_id for c in a] == [c.clause_id for c in b] and len(a) <= 3


def test_returns_nothing_for_an_empty_query():
    assert LocalClauseRetriever().retrieve("", 5) == []
