"""Issue #4 spike: a minimal FEX agent on Amazon Bedrock AgentCore Runtime.

Answers one question: can a tool read a caller-supplied value from `invocation_state`?
- The caller (later: the chat API, #25) sends {"prompt": ..., "producerId": ...}.
- The entrypoint puts producerId into invocation_state. The tool reads it from there.
- The tool has no producer_id parameter, so the model can't see, choose or change it.

Not for producers: no Fair Trade data, no conversation flow. #13, #14 and #25 build on this.
"""
from __future__ import annotations

import json
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool
from strands.types.tools import ToolContext

# Claude via Bedrock with a US inference profile (data stays in US regions). Small model: cheapest.
MODEL_ID = "us.anthropic.claude-haiku-5-5"

SYSTEM = (
    "You are FEX, a test agent for Fair Exchange. When asked whose record this is, call the "
    "whose_record tool and report the producer ID it returns. Answer in one short sentence."
)


@tool(context=True)
def whose_record(tool_context: ToolContext) -> dict:
    """Return the producer ID of this session. The session's producer can't be changed."""
    producer_id = tool_context.invocation_state["producer_id"]  # set by the caller, never by the model
    return {"producer_id": producer_id}


def _default_model():
    from strands.models.bedrock import BedrockModel

    return BedrockModel(model_id=MODEL_ID)


def handle(payload: dict[str, Any], model: Any = None) -> dict[str, Any]:
    producer_id = payload.get("producerId")
    if not isinstance(producer_id, str) or not producer_id.strip():
        return {"error": "producerId is required (set by the API from the signed-in identity)"}

    agent = Agent(model=model or _default_model(), system_prompt=SYSTEM, tools=[whose_record], callback_handler=None)
    result = agent(str(payload.get("prompt", "")), invocation_state={"producer_id": producer_id})

    return {"reply": str(result).strip(), "tool_saw": _tool_results(agent.messages)}


def _tool_results(messages: list[dict]) -> list[str]:
    """Producer IDs the tool returned, so the deployed spike can prove the value reached it.
    Strands stores a dict tool result as JSON text (or a json block, depending on version)."""
    seen = []
    for message in messages:
        for block in message["content"]:
            for part in block.get("toolResult", {}).get("content", []):
                data = part.get("json") or (json.loads(part["text"]) if part.get("text", "").startswith("{") else {})
                if "producer_id" in data:
                    seen.append(data["producer_id"])
    return seen


app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    return handle(payload)


if __name__ == "__main__":
    app.run()
