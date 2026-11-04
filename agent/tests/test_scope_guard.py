"""Scope guard: no tool may let the model choose which producer's data it reads."""
from fex.tools import ALL_TOOLS

FORBIDDEN = {"producer_id", "producerid", "account_sk", "location", "country", "region", "crop",
             "entity_type"}


def test_no_tool_exposes_producer_or_location_parameters():
    for t in ALL_TOOLS:
        params = {p.lower() for p in t.tool_spec["inputSchema"]["json"]["properties"]}
        assert not (params & FORBIDDEN), f"{t.tool_name} exposes {params & FORBIDDEN}"
