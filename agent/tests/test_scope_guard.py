"""Scope guard (#17 contract): no data tool takes a model-settable argument, so the model can call a
tool but cannot steer which producer, place, crop or challenge it reads."""
from fex.tools import ALL_TOOLS


def test_no_data_tool_exposes_any_input_property():
    for t in ALL_TOOLS:
        schema = t.tool_spec["inputSchema"]["json"]
        assert schema.get("properties", {}) == {}, f"{t.tool_name} exposes {sorted(schema['properties'])}"
        assert not schema.get("required"), f"{t.tool_name} requires {schema['required']}"
