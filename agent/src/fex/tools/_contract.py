"""The data tool contract (issue #17, shared contract). Spec: docs/specs/17-standards-grounding.md.

Every data tool (producer record, regional context, peer examples, standards):
  - takes no model-settable arguments; it reads the producer, profile, confirmed tags and summaries from
    the invocation state the engine builds in code;
  - refuses outside the `respond` step;
  - returns a list of EvidenceItem (empty when it finds nothing, never an error for "no data");
  - adds each item's source and kind to the session evidence as it returns them.

The engine calls `run_data_tool` directly for any tool the model skipped (`tool_backstopped`), so a
backstopped call goes through exactly the same checks as a model call.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from fex.tools._scope import retrieval_refusal, session_producer_id
from fex.verifier import SourceKind

# Keys the engine puts in the invocation state for the `respond` step (never set by the model)
EVIDENCE_KEY = "evidence"  # a fex.verifier.SessionEvidence
TOOLS_RUN_KEY = "tools_run"  # set of tool names that returned data in this respond step
ITEMS_KEY = "items"  # every item returned in this respond step, in order, for the answer prompt (#18)
LOG_KEY = "log_tool_call"  # (tool name, items) -> None: the engine logs each data tool run (#26)


class EvidenceItem(TypedDict):
    source: str  # citable label; the model copies it exactly into Citation.source
    kind: SourceKind
    text: str  # plain-English statement of the fact
    period: str | None
    strength: Literal["exact", "nearest", "limited"]
    data: dict[str, Any]  # tool-specific structured fields


@dataclass(frozen=True)
class DataTool:
    name: str  # the Strands tool name
    kind: SourceKind
    fetch: Callable[[dict[str, Any]], list[EvidenceItem]]  # (invocation state) -> items


def run_data_tool(tool: DataTool, state: dict[str, Any]) -> list[EvidenceItem] | dict:
    """Run a data tool under the contract. Returns the items, or the refusal result outside `respond`."""
    if refusal := retrieval_refusal(state):
        return refusal
    session_producer_id(state)  # raises when there is no producer in session
    items = tool.fetch(state)
    if (evidence := state.get(EVIDENCE_KEY)) is not None:
        evidence.record_tool_result(items)
    if (ran := state.get(TOOLS_RUN_KEY)) is not None:
        ran.add(tool.name)
    if (collected := state.get(ITEMS_KEY)) is not None:
        collected.extend(items)
    if (log_call := state.get(LOG_KEY)) is not None:
        log_call(tool.name, items)
    return items
