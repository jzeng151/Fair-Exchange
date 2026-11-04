"""Scope guard (#17 data tool contract): the model can call a data tool but cannot steer what it reads.

Every data tool reads the producer, profile, tags and summaries from the invocation state, so no tool
may expose any input property at all (a deny-list of names let the old `challenge` parameter through).
"""
import pytest

from fex.tools import ALL_TOOLS, DATA_TOOLS


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=lambda t: t.tool_name)
def test_no_data_tool_exposes_any_input_property(tool):
    schema = tool.tool_spec["inputSchema"]["json"]
    assert schema.get("properties", {}) == {}, f"{tool.tool_name} exposes {list(schema['properties'])}"
    assert not schema.get("required")


def test_every_tool_offered_to_the_model_is_under_the_data_tool_contract():
    assert {t.tool_name for t in ALL_TOOLS} == set(DATA_TOOLS)
