"""Negative scope tests (issue #34): data tools never return another producer's data.

Vision doc metric: "0 cases where a data tool returns data for a producer ID or location other
than the one in session."

Every tool in ALL_TOOLS is called through Strands' own stream(), as every sample producer, so the
session context is injected the way the agent does it. The model's only way to influence a tool is
the tool input, so each call is repeated with another producer's identity and location slipped into
the input. Tools added to ALL_TOOLS are covered automatically.

Data tools take no model-settable arguments (#17): the confirmed tags and summaries come from the
session state, so each tool is also called with every session context the engine could give it.
"""
import asyncio
import json

import pytest
from fx_data.peers import PUBLISHABLE, PeerProjects, ProducerProfiles
from fx_data.records import ProducerRecords
from fx_data.regional import RegionalFacts, country_code, normalize, normalize_crops

from fex.models import ChallengeTag
from fex.tools import ALL_TOOLS
from fex.tools.standards import RETRIEVER_KEY, RetrievedClause

PROFILES = ProducerProfiles.load()._profiles
PRODUCERS = sorted(PROFILES)
RECORDS = ProducerRecords.load()
PEER_ROWS = PeerProjects.load()._projects
FACTS = RegionalFacts.load()
TAGS = list(ChallengeTag.__args__)
CLAUSES = ("APS 1.1", "APS 3.6.1", "FPS 1.1")


class StaticRetriever:
    """Stands in for the standards Knowledge Base: the same clauses whoever asks."""

    def retrieve(self, query: str, limit: int) -> list[RetrievedClause]:
        return [RetrievedClause(clause_id=c, standard=c.split()[0], text=f"text of {c}") for c in CLAUSES[:limit]]


def call(tool, tool_input: dict, producer_id: str | None, step: str | None = "respond",
         session: dict | None = None) -> tuple[str, object]:
    """Run a tool the way the agent does. Returns (status, parsed result or error text).

    Data tools only run in the `respond` step (#13), so that is the default session step. `session` holds
    the rest of what the engine puts in the invocation state (confirmed tags, summaries, retriever)."""
    state = {"agent": None} | ({"producer_id": producer_id} if producer_id else {}) \
        | ({"step": step} if step else {}) | (session or {})

    async def run():
        last = None
        async for event in tool.stream({"toolUseId": "scope", "name": tool.tool_name, "input": tool_input}, state):
            last = event
        return last.tool_result

    result = asyncio.run(run())
    text = result["content"][0]["text"]
    return result["status"], (json.loads(text) if result["status"] == "success" else text)


def sessions_for(tool) -> list[dict]:
    """Every session context the engine could give this tool. The model's input is always empty (#17)."""
    if tool.tool_name == "find_peer_examples":
        return [{"tags": [tag]} for tag in TAGS]
    if tool.tool_name == "get_regional_context":
        return [{"tags": list(TAGS)}] + [{"tags": [tag]} for tag in TAGS]
    if tool.tool_name == "find_standards":
        return [{"tags": ["water"], "summary_english": "Rain fell.", RETRIEVER_KEY: StaticRetriever()}]
    return [{}]


def spoof(victim: str) -> dict:
    """Another producer's identity and location, in every spelling a model might try, plus a challenge."""
    p = PROFILES[victim]
    return {"producer_id": victim, "producerId": victim, "account_sk": victim, "country": p["country"],
            "region": p["region"], "location": f"{p['region']}, {p['country']}", "crop": p["crop"],
            "entity_type": p["entity_type"], "challenge": "health", "admin1": p["region"], "tags": ["health"]}


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
    for session in sessions_for(tool):
        status, honest = call(tool, {}, pid, session=session)
        assert status == "success", honest

        # 1. Model-supplied identity, location or challenge changes nothing.
        status, spoofed = call(tool, spoof(victim), pid, session=session)
        assert status == "success" and spoofed == honest, (tool.tool_name, session)

        # 2. No other producer's account id ever appears in a tool result. The producer's own ID may
        #    appear, in their own certification record's source (#14 spec).
        text = json.dumps(honest)
        assert not [a for a in PRODUCERS if a != pid and a in text], tool.tool_name

        # 3. Tool-specific: the producer or location in the result is the session one.
        check = TOOL_CHECKS.get(tool.tool_name)
        assert check, f"add a scope check for new tool {tool.tool_name}"
        check(honest, pid, session)


def _bracket_id(source: str) -> str:
    return source.rsplit("[", 1)[1].rstrip("]")


def _check_record(result, pid, _session):
    assert result == RECORDS.items(pid)
    own = RECORDS.get(pid)
    if own is None:
        assert result == []
        return
    assert all(item["kind"] == "producer_record" for item in result)
    own_refs = {p["project_ref"] for p in own["premium_projects"]}
    projects = [i for i in result if i["source"].startswith("Your Premium project: ")]
    assert {_bracket_id(i["source"]) for i in projects} == own_refs
    # The producer's own ID appears only in their certification record's source
    others = [i for i in result if not i["source"].startswith("Your certification record ")]
    assert pid not in json.dumps(others)


def _check_regional(result, pid, session):
    profile = PROFILES[pid]
    tags = set(session["tags"])
    assert result == FACTS.lookup(profile["country"], profile["region"], normalize_crops(profile["crop"]), tags)
    for item in result:
        row = item["data"]
        assert item["kind"] == "regional" and set(row["tags"].split(";")) & tags
        if row["scope"] in ("region", "country"):
            assert row["country"] == country_code(profile["country"]), "another country's facts"
        if row["scope"] == "region":
            assert normalize(row["admin1"]) == normalize(profile["region"]), "another region's facts"


def _check_peers(result, pid, session):
    by_id = {p["catalog_id"]: p for p in PEER_ROWS}
    for item in result:
        row = by_id[item["source"].rsplit("[", 1)[1].rstrip("]")]
        assert item["kind"] == "peer"
        assert row["owner_producer_id"] != pid, "returned the producer's own project"
        assert set(row["tags"]) & set(session["tags"])
        assert set(item["data"]) == set(PUBLISHABLE), "a field outside the publishable list"


def _check_standards(result, _pid, _session):
    # Clauses only: the same for every producer, and nothing from any producer's record
    assert [i["source"] for i in result] == list(CLAUSES)
    for item in result:
        assert item["kind"] == "standard" and set(item["data"]) <= {"clause_id", "standard", "score"}


TOOL_CHECKS = {
    "get_producer_record": _check_record,
    "get_regional_context": _check_regional,
    "find_peer_examples": _check_peers,
    "find_standards": _check_standards,
}


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_no_producer_in_session_is_refused(tool):
    for session in sessions_for(tool)[:1]:
        status, text = call(tool, {}, None, session=session)
        assert status == "error" and "No producer in session" in text


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_a_spoofed_identity_without_a_session_is_still_refused(tool):
    victim = PRODUCERS[0]
    for session in sessions_for(tool)[:1]:
        status, text = call(tool, spoof(victim), None, session=session)
        assert status == "error" and "No producer in session" in text


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t.tool_name for t in ALL_TOOLS])
def test_unknown_producer_gets_no_producer_data(tool):
    for session in sessions_for(tool):
        status, result = call(tool, {}, "NOT-A-PRODUCER", session=session)
        assert status == "success"
        text = json.dumps(result)
        assert not [a for a in PRODUCERS if a in text]
        # Standards clauses are not producer data; every other tool returns nothing
        assert all(item["kind"] == "standard" for item in result)


def test_every_tool_has_a_scope_check():
    assert {t.tool_name for t in ALL_TOOLS} == set(TOOL_CHECKS)
