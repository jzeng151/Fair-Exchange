"""Call a Strands tool the way the agent does, so tests exercise real context injection."""
import asyncio
import json


def call_tool(tool, tool_input: dict, invocation_state: dict) -> tuple[str, object]:
    """Run `tool` through Strands' own stream(). Returns (status, parsed result or error text)."""
    # Data tools run only in the `respond` step (#13). Tests that call a tool directly are in that
    # step unless they say otherwise (pass "step", or step=None to send no step at all).
    invocation_state = {"step": "respond", **invocation_state}
    if invocation_state["step"] is None:
        del invocation_state["step"]
    async def run():
        last = None
        async for event in tool.stream({"toolUseId": "test", "name": tool.tool_name, "input": tool_input},
                                       {"agent": None, **invocation_state}):
            last = event
        return last.tool_result

    result = asyncio.run(run())
    text = result["content"][0]["text"]
    if result["status"] != "success":
        return result["status"], text
    return result["status"], json.loads(text)
