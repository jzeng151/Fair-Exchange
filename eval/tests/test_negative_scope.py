"""Negative scope tests (issue #34): data tools never return another producer's data.

Vision doc metric: "0 cases where a data tool returns data for a producer ID or location other
than the one in session."

Every tool in ALL_TOOLS is called through Strands' own stream(), as every sample producer, so the
session context is injected the way the agent does it. Data tools take no input (#17 contract), so
the model's only lever is input the schema does not declare: each call is repeated with another
producer's identity, location and challenge tags slipped into the input. The confirmed tags come
from the session, so each producer is run with every tag. Tools added to ALL_TOOLS are covered
automatically.
"""
import asyncio
import json

import pytest
from fx_data.peers import PeerProjects, ProducerProfiles, owner_key
from fx_data.records import ProducerRecords
from fx_data.regional import RegionalFacts, country_code, normalize, normalize_crops

from fex.models import ChallengeTag
from fex.tools import ALL_TOOLS

PROFILES = ProducerProfiles.load()._profiles
PRODUCERS = sorted(PROFILES)
RECORDS = ProducerRecords.load()
PEER_ROWS = {p["catalog_id"]: p for p in PeerProjects.load()._projects}
FACTS = RegionalFacts.load()
TAGS = list(ChallengeTag.__args__)
# Session tag sets: every tag at once, then each tag alone.
TAG_SETS = [TAGS] + [[t] for t in TAGS]


def call(tool, tool_input: dict, producer_id: str | None, tags=TAGS, step: str | None = "respond"
         ) -> tuple[str, object]:
    """Run a tool the way the agent does. Returns (status, parsed result or error text).

    Data tools only run in the `respond` step (#13), so that is the default session step."""
    state = {"agent": None, "tags": list(tags)} | ({"producer_id": producer_id} if producer_id else {}) \
        | ({"step": step} if step else {})

    async def run():
        last = None
        async for event in tool.stream({"toolUseId": "scope", "name": tool.tool_name, "input": tool_input}, state):
            last = event
        return last.tool_result

    result = asyncio.run(run())
    text = result["content"][0]["text"]
    return result["status"], (json.loads(text) if result["status"] == "success" else text)


def spoof(victim: str, tags: list[str]) -> dict:
    """Another producer's identity and location, in every spelling a model might try, and other tags."""
    p = PROFILES[victim]
    other = [t for t in TAGS if t not in tags] or ["education"]
    return {"producer_id": victim, "producerId": victim, "account_sk": victim, "country": p["country"],
            "region": p["region"], "admin1": p["region"], "location": f"{p['region']}, {p['country']}",
            "crop": p["crop"], "crops": [p["crop"]], "entity_type": p["entity_type"], "tags": other,
            "challenge": other[0]}


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
    for tags in TAG_SETS:
        status, honest = call(tool, {}, pid, tags)
        assert status == "success", honest

        # 1. Model-supplied identity, location or tags change nothing.
        status, spoofed = call(tool, spoof(victim, tags), pid, tags)
        assert status == "success" and spoofed == honest, (tool.tool_name, tags)

        # 2. No other producer's account id ever appears in a tool result. The producer's own ID
        #    may appear, in their own certification record's source (#14 spec).
        text = json.dumps(honest)
        assert not [a for a in PRODUCERS if a != pid and a in text], tool.tool_name

        # 3. Tool-specific: the producer or location in the result is the session one.
        check = TOOL_CHECKS.get(tool.tool_name)
        assert check, f"add a scope check for new tool {tool.tool_name}"
        check(honest, pid, set(tags))


def _bracket_id(source: str) -> str:
    return source.rsplit("[", 1)[1].rstrip("]")


def _check_record(result, pid, _):
    assert result == RECORDS.items(pid)
    own_refs = {p["project_ref"] for p in RECORDS.get(pid)["premium_projects"]}
    project_ids = {_bracket_id(i["source"]) for i in result if i["source"].startswith("Your Premium project: ")}
    assert project_ids == own_refs
    assert pid not in json.dumps([i for i in result if not i["source"].startswith("Your certification record ")])


def _check_regional(result, pid, tags):
    profile = PROFILES[pid]
    assert result == FACTS.lookup(profile["country"], profile["region"], normalize_crops(profile["crop"]), tags)
    for item in result:
        row = item["data"]
        if row["scope"] == "region":
            assert normalize(row["admin1"]) == normalize(profile["region"]), "another region's facts"
        if row["scope"] in ("region", "country"):
            assert row["country"] == country_code(profile["country"]), "another country's facts"
        assert set(row["tags"].split(";")) & tags


def _check_peers(result, pid, tags):
    own = owner_key(pid)
    for item in result:
        row = PEER_ROWS[_bracket_id(item["source"])]
        assert row["owner_key"] != own, "returned the producer's own project"
        assert set(row["tags"]) & tags
        assert "owner_key" not in json.dumps(item)


TOOL_CHECKS = {
    "get_producer_record": _check_record,
    "get_regional_context": _check_regional,
    "find_peer_examples": _check_peers,
}


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_no_producer_in_session_is_refused(tool):
    status, text = call(tool, {}, None)
    assert status == "error" and "No producer in session" in text


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_a_spoofed_identity_without_a_session_is_still_refused(tool):
    status, text = call(tool, spoof(PRODUCERS[0], TAGS), None)
    assert status == "error" and "No producer in session" in text


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_unknown_producer_gets_no_producer_data(tool):
    status, result = call(tool, {}, "NOT-A-PRODUCER")
    assert status == "success" and result == []


def test_every_tool_has_a_scope_check():
    assert {t.tool_name for t in ALL_TOOLS} == set(TOOL_CHECKS)
