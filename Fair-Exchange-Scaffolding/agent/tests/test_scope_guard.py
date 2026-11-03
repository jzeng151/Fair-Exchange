"""Scope guard: no tool may let the model choose which producer's data it reads.
TODO(#34): add negative tests that call tools with a different producer in the prompt."""
import inspect

from fex.tools import ALL_TOOLS

FORBIDDEN = {"producer_id", "producerid", "account_sk", "location", "country", "region"}


def test_no_tool_exposes_producer_or_location_parameters():
    for t in ALL_TOOLS:
        fn = getattr(t, "_tool_func", None) or getattr(t, "original_function", None) or t
        params = {p.lower() for p in inspect.signature(fn).parameters} - {"tool_context"}
        assert not (params & FORBIDDEN), f"{t} exposes {params & FORBIDDEN}"
