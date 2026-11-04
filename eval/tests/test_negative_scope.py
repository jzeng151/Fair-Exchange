"""Negative scope tests (issue #34): data tools never return another producer's data.

Vision doc metric: "0 cases where a data tool returns data for a producer ID or location other
than the one in session."

Every tool in ALL_TOOLS is called through Strands' own stream(), as every sample producer, so the
session context is injected the way the agent does it. The model's only way to influence a tool is
the tool input, so each call is repeated with another producer's identity and location slipped into
the input. Tools added to ALL_TOOLS are covered automatically.
"""
import asyncio
import json

import pytest
from fx_data.peers import PeerProjects, ProducerProfiles, owner_key
from fx_data.records import ProducerRecords
from fx_data.regional import RegionalFacts

from fex.models import ChallengeTag
from fex.tools import ALL_TOOLS

PROFILES = ProducerProfiles.load()._profiles
PRODUCERS = sorted(PROFILES)
RECORDS = ProducerRecords.load()._records
PEER_ROWS = PeerProjects.load()._projects
TAGS = list(ChallengeTag.__args__)


def call(tool, tool_input: dict, producer_id: str | None, step: str | None = "respond") -> tuple[str, object]:
    """Run a tool the way the agent does. Returns (status, parsed result or error text).

    Data tools only run in the `respond` step (#13), so that is the default session step."""
    state = {"agent": None} | ({"producer_id": producer_id} if producer_id else {}) \
        | ({"step": step} if step else {})

    async def run():
        last = None
        async for event in tool.stream({"toolUseId": "scope", "name": tool.tool_name, "input": tool_input}, state):
            last = event
        return last.tool_result

    result = asyncio.run(run())
    text = result["content"][0]["text"]
    return result["status"], (json.loads(text) if result["status"] == "success" else text)


def inputs_for(tool) -> list[dict]:
    """Every legitimate input the model could send this tool."""
    props = tool.tool_spec["inputSchema"]["json"]["properties"]
    return [{"challenge": tag} for tag in TAGS] if "challenge" in props else [{}]


def spoof(victim: str) -> dict:
    """Another producer's identity and location, in every spelling a model might try."""
    p = PROFILES[victim]
    return {"producer_id": victim, "producerId": victim, "account_sk": victim, "country": p["country"],
            "region": p["region"], "location": f"{p['region']}, {p['country']}", "crop": p["crop"],
            "entity_type": p["entity_type"]}


def victim_for(pid: str) -> str:
    """A different producer in a different region, so a leak would be visible."""
    me = PROFILES[pid]
    return next(v for v in PRODUCERS if v != pid and PROFILES[v]["region"] != me["region"])


CASES = [(tool, pid) for tool in ALL_TOOLS for pid in PRODUCERS]


def _id(case):
    tool, pid = case
    return f"{tool.tool_name}-{pid[:8]}"


@pytest.mark.parametrize("case", CASES, ids=[_id(c) for c in CASES])
def test_tool_returns_only_session_scoped_data(case):
    tool, pid = case
    victim = victim_for(pid)
    for tool_input in inputs_for(tool):
        status, honest = call(tool, tool_input, pid)
        assert status == "success", honest

        # 1. Model-supplied identity or location changes nothing.
        status, spoofed = call(tool, tool_input | spoof(victim), pid)
        assert status == "success" and spoofed == honest, (tool.tool_name, tool_input)

        # 2. No producer's account id ever appears in a tool result.
        text = json.dumps(honest)
        assert not [a for a in PRODUCERS if a in text], tool.tool_name

        # 3. Tool-specific: the producer or location in the result is the session one.
        check = TOOL_CHECKS.get(tool.tool_name)
        assert check, f"add a scope check for new tool {tool.tool_name}"
        check(honest, pid, tool_input)


def _check_record(result, pid, _):
    own = RECORDS[pid]
    assert result == {"found": True, **own}
    own_refs = {p["project_ref"] for p in own["premium_projects"]}
    assert {p["project_ref"] for p in result["premium_projects"]} == own_refs


def _check_regional(result, pid, _):
    profile = PROFILES[pid]
    if "region" in result:
        assert result["region"] == {"country": profile["country"], "region": profile["region"],
                                    "crop": profile["crop"]}
    expected = RegionalFacts.load().lookup(profile["country"], profile["region"], profile["crop"]).as_dict()
    assert result["facts"] == expected["facts"]


def _check_peers(result, pid, tool_input):
    own = owner_key(pid)
    by_ref = {p["project_ref"]: p for p in PEER_ROWS}
    for item in result:
        assert by_ref[item["project_ref"]]["owner_key"] != own, "returned the producer's own project"
        assert item["challenge_tag"] == tool_input["challenge"]
        assert "owner_key" not in item


TOOL_CHECKS = {
    "get_producer_record": _check_record,
    "get_regional_context": _check_regional,
    "find_peer_examples": _check_peers,
}


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_no_producer_in_session_is_refused(tool):
    for tool_input in inputs_for(tool)[:1]:
        status, text = call(tool, tool_input, None)
        assert status == "error" and "No producer in session" in text


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_a_spoofed_identity_without_a_session_is_still_refused(tool):
    victim = PRODUCERS[0]
    for tool_input in inputs_for(tool)[:1]:
        status, text = call(tool, tool_input | spoof(victim), None)
        assert status == "error" and "No producer in session" in text


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_unknown_producer_gets_no_producer_data(tool):
    for tool_input in inputs_for(tool):
        status, result = call(tool, tool_input, "NOT-A-PRODUCER")
        assert status == "success"
        text = json.dumps(result)
        assert not [a for a in PRODUCERS if a in text]
        if isinstance(result, dict):
            assert not result.get("premium_projects") and not result.get("facts")
        else:
            assert result == []


def test_every_tool_has_a_scope_check():
    assert {t.tool_name for t in ALL_TOOLS} == set(TOOL_CHECKS)
