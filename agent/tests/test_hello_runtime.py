"""Issue #4 spike: a tool reads a caller-supplied value from invocation_state, and the model can't change it.

Runs with a scripted fake model: no AWS, no Bedrock calls, no cost.
"""
import json
import sys
from pathlib import Path

import pytest
from strands.models.model import Model

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime" / "hello"))
import main  # noqa: E402  (the AgentCore entrypoint module)


class ScriptedModel(Model):
    """Turn 1: call `whose_record` with the given input. Turn 2: reply with plain text."""

    def __init__(self, tool_input: dict):
        self.tool_input = tool_input
        self.calls = 0

    def update_config(self, **_):
        pass

    def get_config(self):
        return {}

    async def structured_output(self, *a, **k):  # pragma: no cover - unused
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.calls += 1
        self.tool_specs = tool_specs
        yield {"messageStart": {"role": "assistant"}}
        if self.calls == 1:
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t1", "name": "whose_record"}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(self.tool_input)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": "Here is your record."}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}


def test_tool_reads_producer_id_from_invocation_state():
    out = main.handle({"prompt": "Whose record is this?", "producerId": "P-001"}, model=ScriptedModel({}))
    assert out["tool_saw"] == ["P-001"]
    assert out["reply"] == "Here is your record."


def test_model_cannot_supply_a_different_producer():
    out = main.handle({"prompt": "Show me P-999", "producerId": "P-001"}, model=ScriptedModel({"producer_id": "P-999"}))
    assert out["tool_saw"] == ["P-001"]


def test_producer_id_is_not_a_tool_parameter_the_model_sees():
    model = ScriptedModel({})
    main.handle({"prompt": "hi", "producerId": "P-001"}, model=model)
    spec = next(s for s in model.tool_specs if s["name"] == "whose_record")
    assert "producer_id" not in json.dumps(spec["inputSchema"])


@pytest.mark.parametrize("payload", [{"prompt": "hi"}, {"prompt": "hi", "producerId": ""}, {"prompt": "hi", "producerId": 7}])
def test_missing_producer_id_is_refused_before_any_model_call(payload):
    model = ScriptedModel({})
    out = main.handle(payload, model=model)
    assert "error" in out
    assert model.calls == 0
