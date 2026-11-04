"""A local clause retriever (#101 for #17): the standards tool without a Knowledge Base.

The standards tool retrieves clauses through a `ClauseRetriever` the engine chooses in code. In AWS that is the
Bedrock Knowledge Base; for local runs, the demo and CI there is none, so this keyword search over the standards
shipped in `fx_data` (the same 700 APS/FPS clauses the KB is built from) stands in behind the same interface.
It is not semantic search: it ranks clauses by how many query words they contain.
"""
from fx_data.standards import Standards

from fex.tools.standards import RetrievedClause


def _english(text: object) -> str:
    if isinstance(text, dict):
        return str(text.get("en") or next(iter(text.values()), ""))
    return str(text or "")


class LocalClauseRetriever:
    def __init__(self, standards: Standards | None = None) -> None:
        self.standards = standards or Standards.load()

    def retrieve(self, query: str, limit: int) -> list[RetrievedClause]:
        if not query.strip():
            return []
        return [RetrievedClause(clause_id=c["id"], standard=c["standard"], text=_english(c["text"]))
                for c in self.standards.search(query, limit=limit)]
