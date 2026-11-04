"""Export the conversation record schema as JSON Schema (deterministic text)."""
import json

from pydantic import TypeAdapter

from fex.models import ConversationRecord


def export_json_schema() -> str:
    """JSON Schema for a conversation record (completed or declined), as stable, sorted text."""
    schema = TypeAdapter(ConversationRecord).json_schema()
    schema["title"] = "ConversationRecord"
    schema["description"] = (
        "One record per Fair Exchange conversation. Generated from agent/src/fex/models.py; do not edit by hand."
    )
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
