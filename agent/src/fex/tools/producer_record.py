"""Producer-record tool (issue #14): this producer's own profile, Premium projects and survey context.

Follows the data tool contract (#17, fex.tools._contract). Fields and source labels are still the merged
#62 behavior; aligning them with docs/specs/14-producer-record-tool.md is the #14 retro.
"""
from functools import lru_cache
from typing import Any

from fx_data.records import ProducerRecords
from strands import tool
from strands.types.tools import ToolContext

from fex.tools._contract import DataTool, EvidenceItem, run_data_tool
from fex.tools._scope import session_producer_id


@lru_cache(maxsize=1)
def _records() -> ProducerRecords:
    return ProducerRecords.load()


def _without_source(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "source"}


def _profile_item(profile: dict) -> EvidenceItem:
    place = ", ".join(p for p in (profile.get("region"), profile.get("country")) if p)
    text = "; ".join(part for part in (
        f"Location on file: {place}" if place else "",
        f"crop: {profile['crop']}" if profile.get("crop") else "",
        f"entity type: {profile['entity_type']}" if profile.get("entity_type") else "",
        f"certification scope: {profile['certification_scope']}" if profile.get("certification_scope") else "",
    ) if part)
    return EvidenceItem(source=profile["source"], kind="producer_record", text=text or "Producer profile on file.",
                        period=None, strength="exact", data=_without_source(profile))


def _project_item(project: dict) -> EvidenceItem:
    period = " to ".join(d for d in (project.get("start_date"), project.get("end_date")) if d) or None
    status = f" ({project['status']})" if project.get("status") else ""
    return EvidenceItem(source=project["source"], kind="producer_record",
                        text=f"Your Premium project {project['name']}{status}: {project['action']}",
                        period=period, strength="exact", data=_without_source(project))


def _survey_item(fact: dict) -> EvidenceItem:
    return EvidenceItem(source=fact["source"], kind="producer_record", text=fact["text"], period=fact.get("period"),
                        strength=fact.get("strength", "exact"), data=_without_source(fact))


def _fetch(state: dict[str, Any]) -> list[EvidenceItem]:
    record = _records().get(session_producer_id(state))
    if record is None:
        return []
    return ([_profile_item(record["profile"])]
            + [_project_item(p) for p in record["premium_projects"]]
            + [_survey_item(f) for f in record["survey"]["facts"]])


PRODUCER_RECORD = DataTool("get_producer_record", "producer_record", _fetch)


@tool(context=True)
def get_producer_record(tool_context: ToolContext) -> list | dict:
    """Return this producer's own profile, Premium projects and safe survey facts (farming, water, practices only).

    Each item has: source (cite it exactly), kind, text, period, strength and data. The first item is the
    profile; then their own Premium projects; then survey facts. No survey facts is normal: say so rather
    than guess. An empty list means there is no record on file for this producer.
    """
    return run_data_tool(PRODUCER_RECORD, tool_context.invocation_state)
