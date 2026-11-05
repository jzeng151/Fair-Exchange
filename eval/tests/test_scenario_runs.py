"""Seam 1 (#35): every scenario run drives the agent entrypoint end to end with a scripted fake model.

The deterministic demo model (#101) stands in for Bedrock, the data tools and the citation verifier are
the real ones, and a fake PII scanner stands in for Comprehend. The runner behaves as the spec says: it
reads each turn's events to the end, checks the expected step arrived and that the next action is
allowed, and answers extra intake questions from `intake_replies`. Expected outcomes are checked except
tags, which need the real model, and out-of-scope handling, whose detector is not decided (#21).
"""
import json
import re
from pathlib import Path

import pytest

from fex.conversation import ConversationEngine, InMemoryStateStore
from fex.conversation.demo_model import DemoModel
from fex.conversation.runtime import invoke
from fex.models import parse_record
from fex.records.local import FileRecordStore
from fex.tools.standards import LocalClauseRetriever

EVAL = Path(__file__).parents[1]
RUNS = sorted((EVAL / "scenarios").glob("S*.json")) + sorted((EVAL / "scenarios" / "contrast").glob("*.json"))
LAST_REPLY = "That's all I can add."

# The invented person in S5. Detecting names is Comprehend's job; this checks what the agent does with a hit.
KNOWN_NAMES = ["Kouame Konan"]
PHONE = re.compile(r"\+\d[\d ]{8,}\d")


def fake_pii_scanner(text: str, language: str) -> list[dict]:
    """Comprehend's response shape for the invented name and any international phone number."""
    spans = [(m, "NAME") for name in KNOWN_NAMES for m in re.finditer(re.escape(name), text)]
    spans += [(m, "PHONE") for m in PHONE.finditer(text)]
    return [{"Type": kind, "Score": 0.99, "BeginOffset": m.start(), "EndOffset": m.end()}
            for m, kind in sorted(spans, key=lambda s: s[0].start())]


def run_scenario(scenario: dict, records_dir: Path) -> tuple[list[dict], list[str]]:
    model = DemoModel()
    engine = ConversationEngine(store=InMemoryStateStore(), small_model=model, large_model=model,
                                records=FileRecordStore(records_dir), retriever=LocalClauseRetriever(),
                                pii_scanner=fake_pii_scanner)
    ids = {"producerId": scenario["producer_id"], "conversationId": scenario["scenario_id"]}
    replies = list(scenario["intake_replies"])
    problems: list[str] = []

    def send(body: dict) -> list[dict]:
        result = invoke({**ids, **body}, engine)
        assert "events" in result, result
        return result["events"]

    events = send({"kind": "start"})
    seen = list(events)
    for n, turn in enumerate(scenario["turns"], start=1):
        allowed = next((e["allowed"] for e in reversed(events) if e["type"] == "actions"), [])
        if "action" in turn and turn["action"]["name"] not in allowed:
            problems.append(f"turn {n}: {turn['action']['name']} not in allowed actions {allowed}")
        body = {"kind": "message", "text": turn["message"]} if "message" in turn else {"kind": "action", "action": turn["action"]}
        events = send(body)
        steps = [e["step"] for e in events if e["type"] == "step"]
        # Extra intake questions: answer them until the expected later step arrives
        while turn["expect_step"] != "intake" and steps[-1:] == ["intake"]:
            events = send({"kind": "message", "text": replies.pop(0) if replies else LAST_REPLY})
            steps = [e["step"] for e in events if e["type"] == "step"]
            seen += events
        seen += events
        if errors := [e["code"] for e in events if e["type"] == "error"]:
            problems.append(f"turn {n}: error events {errors}")
        if turn["expect_step"] not in steps:
            problems.append(f"turn {n}: expected step {turn['expect_step']}, got {steps}")
    return seen, problems


@pytest.mark.parametrize("path", RUNS, ids=[p.stem for p in RUNS])
def test_scenario_runs_end_to_end_with_its_expected_outcome(path, tmp_path):
    scenario = json.loads(path.read_text(encoding="utf-8"))
    events, problems = run_scenario(scenario, tmp_path)
    assert problems == []
    expected = scenario["expected"]
    answers = [e for e in events if e["type"] == "answer"]
    assert answers and answers[-1]["evidence"] == expected["evidence"]
    record = parse_record(json.loads((tmp_path / f"{scenario['scenario_id']}.json").read_text(encoding="utf-8")))
    assert record.status == expected["record_status"]
    assert record.consent.scope == expected["consent_scope"]
    assert getattr(record, "pii_flag", False) == expected["pii_flag"]
    assert list(getattr(record, "pii_entity_types", [])) == expected["pii_entity_types"]


def test_the_fake_scanner_finds_only_the_invented_person_and_phone():
    text = "The technician Kouame Konan came, call him at +225 07 00 00 00 00. Fair Trade helps."
    found = fake_pii_scanner(text, "en")
    assert [(e["Type"], text[e["BeginOffset"]:e["EndOffset"]]) for e in found] == [
        ("NAME", "Kouame Konan"), ("PHONE", "+225 07 00 00 00 00")]
