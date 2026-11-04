"""Scenario and labeled-set files (#35) are well formed, so the demo runner and eval harness (#36)
can rely on them. This checks the files, not the agent: running the scenarios end to end needs the
conversation steps (#13) and the chat endpoint (#25)."""
import json
from pathlib import Path

import pytest
from fx_data.peers import ProducerProfiles

from fex.models import ChallengeTag

EVAL = Path(__file__).parents[1]
SCENARIOS = sorted((EVAL / "scenarios").glob("*.json"))
LABELS = json.loads((EVAL / "labeled" / "challenge-tags.json").read_text(encoding="utf-8"))["items"]
TAGS = set(ChallengeTag.__args__)
PROFILES = ProducerProfiles.load()._profiles

# Actions and arguments from docs/specs/13-conversation-steps.md
ACTIONS = {
    "confirm_playback": {}, "reopen_playback": {}, "retry_answer": {}, "end": {},
    "correct_playback": {"text": None},
    "set_consent": {"scope": {"internal", "internal_and_outward", "declined"}},
    "set_feedback": {"value": {"yes", "somewhat", "no"}},
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_required_scenarios_exist():
    s = [_load(p) for p in SCENARIOS]
    assert len(s) >= 3
    assert any(x["language"] == "es" for x in s), "at least one Spanish scenario"
    assert any(x["expect"]["record"]["status"] == "declined" for x in s), "decline path"
    assert any(x["expect"]["record"]["pii_flag"] for x in s), "PII flag path"
    countries = {PROFILES[x["producer_id"]]["country"] for x in s}
    assert {"Colombia", "Mexico", "Vietnam"} <= countries, "the vision doc's three scenarios"


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario_is_well_formed(path):
    s = _load(path)
    assert s["id"] == path.stem
    assert s["producer_id"] in PROFILES, "must be a sample producer, so the tools have data"
    assert s["language"] in {"en", "es", "fr"}  # fr added with the French exchange (#24)
    turns = s["turns"]
    assert turns[0] == {"kind": "start"} and turns[-1]["kind"] == "action"
    for t in turns:
        assert t["kind"] in {"start", "message", "action"}
        assert "producer_id" not in json.dumps(t).lower() and "producerid" not in json.dumps(t).lower()
        if t["kind"] == "message":
            assert 1 <= len(t["text"]) <= 4000
        if t["kind"] == "action":
            name, args = t["action"]["name"], t["action"]["args"]
            assert name in ACTIONS, name
            assert set(args) == set(ACTIONS[name]), (name, args)
            for key, allowed in ACTIONS[name].items():
                if allowed:
                    assert args[key] in allowed, (name, args)
    exp = s["expect"]
    assert exp["tags"] and set(exp["tags"]) <= TAGS
    assert exp["evidence"] in {"full", "limited"}
    assert exp["record"]["status"] in {"completed", "declined"}


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_expected_record_matches_the_last_choices(path):
    s = _load(path)
    actions = [t["action"] for t in s["turns"] if t["kind"] == "action"]
    consent = [a["args"]["scope"] for a in actions if a["name"] == "set_consent"]
    feedback = [a["args"]["value"] for a in actions if a["name"] == "set_feedback"]
    rec = s["expect"]["record"]
    assert rec["consent_scope"] == consent[-1]
    assert rec["status"] == ("declined" if consent[-1] == "declined" else "completed")
    assert rec["feedback"] == (feedback[-1] if feedback and consent[-1] != "declined" else None)
    if "consent_history" in s["expect"]:
        assert s["expect"]["consent_history"] == consent


def test_labeled_set_covers_every_tag():
    used = {tag for item in LABELS for tag in item["tags"]}
    assert used == TAGS
    for tag in TAGS:
        assert sum(tag in item["tags"] for item in LABELS) >= 2, tag


def test_labeled_items_are_well_formed():
    ids = [item["id"] for item in LABELS]
    assert len(ids) == len(set(ids))
    for item in LABELS:
        assert item["language"] in {"en", "es"} and item["text"].strip()
        assert item["tags"] and set(item["tags"]) <= TAGS
        assert item["labeled_by"]
    assert {item["language"] for item in LABELS} == {"en", "es"}
