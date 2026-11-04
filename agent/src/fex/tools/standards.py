"""Standards tool (issue #17): the APS/FPS clauses related to the producer's confirmed challenge.

Spec: docs/specs/17-standards-grounding.md. Follows the data tool contract (fex.tools._contract).
  - Query: the confirmed playback's English summary (the original summary for English conversations)
    plus its tags, so Spanish and English conversations get the same results.
  - Results: the top 5 clauses from the standards Knowledge Base (one document per clause, no chunking).
  - Every returned clause ID is recorded in the session evidence; a claim may only cite those clauses.

The retriever is chosen in code by the engine and passed in the invocation state, never by the model.
Tests use a fake retriever behind the same `ClauseRetriever` interface.
"""
import os
from dataclasses import dataclass
from typing import Any, Protocol

from fx_data.standards import normalize_id
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._contract import DataTool, EvidenceItem, run_data_tool
from fex.tools._scope import session_tags

TOP_K = 5
MAX_QUERY_CHARS = 1000
RETRIEVER_KEY = "clause_retriever"  # invocation state key, set by the engine
KB_ID_ENV = "FEX_STANDARDS_KB_ID"


@dataclass(frozen=True)
class RetrievedClause:
    clause_id: str
    standard: str
    text: str
    score: float | None = None


class ClauseRetriever(Protocol):
    def retrieve(self, query: str, limit: int) -> list[RetrievedClause]: ...


class BedrockKbRetriever:
    """Amazon Bedrock Knowledge Base retrieval (S3 Vectors store, Titan Text Embeddings V2)."""

    def __init__(self, knowledge_base_id: str, client: Any = None) -> None:
        self.knowledge_base_id = knowledge_base_id
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-agent-runtime")
        return self._client

    def retrieve(self, query: str, limit: int) -> list[RetrievedClause]:
        response = self.client.retrieve(
            knowledgeBaseId=self.knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": limit}},
        )
        clauses = []
        for result in response.get("retrievalResults", []):
            metadata = result.get("metadata") or {}
            clause_id = normalize_id(str(metadata.get("clause_id", "")))
            if clause_id:
                clauses.append(RetrievedClause(clause_id=clause_id, standard=str(metadata.get("standard", "")),
                                               text=(result.get("content") or {}).get("text", ""),
                                               score=result.get("score")))
        return clauses


def default_retriever() -> ClauseRetriever | None:
    """The Bedrock retriever when the Knowledge Base ID is configured (set by the deploy), else None."""
    kb_id = os.environ.get(KB_ID_ENV)
    return BedrockKbRetriever(kb_id) if kb_id else None


def standards_query(state: dict[str, Any]) -> str:
    summary = state.get("summary_english") or state.get("summary_original") or ""
    tags = session_tags(state)
    query = " ".join(part for part in (summary.strip(), ("Challenges: " + ", ".join(tags)) if tags else "") if part)
    return query[:MAX_QUERY_CHARS]


def _fetch(state: dict[str, Any]) -> list[EvidenceItem]:
    retriever: ClauseRetriever | None = state.get(RETRIEVER_KEY)
    if retriever is None:
        raise RuntimeError(f"The standards Knowledge Base is not configured ({KB_ID_ENV})")
    query = standards_query(state)
    if not query:
        return []
    items, seen = [], set()
    for clause in retriever.retrieve(query, TOP_K):
        clause_id = normalize_id(clause.clause_id)
        if not clause_id or clause_id in seen:
            continue
        seen.add(clause_id)
        items.append(EvidenceItem(source=clause_id, kind="standard", text=clause.text, period=None,
                                  strength="exact",
                                  data={"clause_id": clause_id, "standard": clause.standard, "score": clause.score}))
    return items[:TOP_K]


STANDARDS = DataTool("find_standards", "standard", _fetch)


@tool(context=True)
def find_standards(tool_context: ToolContext) -> list | dict:
    """Find the Fair Trade standard (APS or FPS) clauses related to the producer's confirmed challenge.

    Each item has: source (the clause ID), kind, text (the clause), and data.clause_id. Cite one of these
    clause IDs exactly as each claim's standard_clause; no other clause will pass the citation check.
    """
    return run_data_tool(STANDARDS, tool_context.invocation_state)
