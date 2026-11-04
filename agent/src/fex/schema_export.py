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


def export_contract_schema() -> str:
    """JSON Schema for the chat API <-> agent contract (#13): requests, actions, events, resume."""
    from fex.conversation.contract import ConversationContract

    schema = TypeAdapter(ConversationContract).json_schema(by_alias=True)
    schema["title"] = "ConversationContract"
    schema["description"] = (
        "Requests, actions and events between the chat API and the agent. Generated from "
        "agent/src/fex/conversation/contract.py; do not edit by hand."
    )
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
