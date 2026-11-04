"""Issue #89: the agent runtime's wire format, as the chat API (#25) reads it.

The AgentCore Python SDK streams a generator entrypoint as Server-Sent Events (`data: <json>` + blank line) and
returns a plain dict as `application/json`. The chat API's parser is tested against fixtures made HERE with the
SDK's own SSE encoder, so both sides check the same bytes. Regenerate with:
    FEX_WRITE_WIRE_FIXTURES=1 uv run pytest tests/test_wire_format.py
"""
import json
import os
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from tests.conversation_harness import RETRIEVE, Run, summary

from fex.conversation import runtime

FIXTURES = Path(__file__).resolve().parents[2] / "api" / "src" / "core" / "fixtures"


def scripted_turn():
    """A real engine turn with every event type a happy path produces: text, step, claims, answer, actions, done."""
    r = Run()
    r.conversation_id = "11111111-2222-4333-8444-555555555555"
    r.to_playback()
    r.small.add(summary())
    r.large.add(*RETRIEVE, r.good_answer())
    request = {"kind": "action", "producerId": r.producer_id, "conversationId": r.conversation_id,
               "action": {"name": "confirm_playback", "args": {}}}
    return r, request


def sse_bytes(events) -> bytes:
    app = BedrockAgentCoreApp()
    return b"".join(app._convert_to_sse(e) for e in events)


def check_fixture(name: str, content: bytes) -> None:
    path = FIXTURES / name
    if os.environ.get("FEX_WRITE_WIRE_FIXTURES"):
        path.write_bytes(content)
    assert path.read_bytes() == content, f"{name} is stale: regenerate with FEX_WRITE_WIRE_FIXTURES=1"


def test_streaming_requests_are_a_generator_of_contract_events():
    r, request = scripted_turn()
    out = runtime.respond(request, engine=r.engine)
    assert not isinstance(out, dict)  # the SDK streams generators as SSE
    events = list(out)
    assert events[-1]["type"] == "done" and all("type" in e and "seq" in e for e in events)


def test_resume_is_a_plain_object_with_step_at_the_top():
    r, _ = scripted_turn()
    out = runtime.respond({"kind": "resume", "producerId": r.producer_id, "conversationId": r.conversation_id},
                          engine=r.engine)
    assert isinstance(out, dict) and out["step"] == "playback" and "resume" not in out
    json.dumps(out)  # what the SDK returns as application/json


def test_a_malformed_request_streams_a_contract_error_event_then_done():
    out = list(runtime.respond({"kind": "message", "producerId": "P", "conversationId": "c", "text": ""},
                               engine=Run().engine))
    assert [e["type"] for e in out] == ["error", "done"]
    assert out[0]["code"] == "agent_failed" and out[0]["seq"] == 1 and out[1]["seq"] == 2


def test_stream_fixture_matches_what_the_sdk_sends():
    r, request = scripted_turn()
    events = list(runtime.respond(request, engine=r.engine))
    check_fixture("agent-stream.sse", sse_bytes(events))
    check_fixture("agent-stream.events.json", (json.dumps(events, ensure_ascii=False, indent=2) + "\n").encode())


def test_resume_fixture_matches_what_the_sdk_returns():
    r, _ = scripted_turn()
    out = runtime.respond({"kind": "resume", "producerId": r.producer_id, "conversationId": r.conversation_id},
                          engine=r.engine)
    check_fixture("agent-resume.json", (json.dumps(out, ensure_ascii=False, indent=2) + "\n").encode())
