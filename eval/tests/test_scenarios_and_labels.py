"""Scenario and labeled-set files (#35) are well formed, so the demo runner and eval harness (#36)
can rely on them. This checks the files, not the agent: running the scenarios end to end needs the
conversation steps (#13) and the chat endpoint (#25). The format follows
docs/specs/35-scenarios-and-labels.md: scenario_id, turns of a message or an action each naming the
step it expects, intake_replies, and the expected record."""
import json
from pathlib import Path

import pytest
from fx_data.peers import ProducerProfiles

from fex.conversation.engine import ALLOWED
from fex.models import ChallengeTag

EVAL = Path(__file__).parents[1]
SCENARIOS = sorted((EVAL / "scenarios").glob("S*.json"))
# #7's contrast pairs need one run per producer; producers not already in S1 to S7 have their own file (#35)
CONTRAST = sorted((EVAL / "scenarios" / "contrast").glob("*.json"))
RUNS = SCENARIOS + CONTRAST
DEFINITIONS = json.loads((EVAL.parent / "data" / "generator_inputs" / "producer_definitions.json").read_text(encoding="utf-8"))
LABELS = [json.loads(line) for line in (EVAL / "labeled" / "challenge-tags.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
TAGS = set(ChallengeTag.__args__)
PROFILES = ProducerProfiles.load()._profiles
REQUIRED_IDS = {"S1", "S2", "S3", "S4", "S5", "S6", "S7"}
STEPS = {"intake", "playback", "respond", "consent", "feedback", "closed"}
PII_TYPES = {"NAME", "PHONE", "EMAIL", "ADDRESS"}

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
    assert {x["scenario_id"] for x in s} == REQUIRED_IDS
    assert len(s) == len(SCENARIOS) == 7
    assert any(x["language"] == "es" for x in s), "at least one Spanish scenario"
    assert any(x["expected"]["record_status"] == "declined" for x in s), "decline path"
    assert any(x["expected"]["pii_flag"] for x in s), "PII flag path"
    countries = {PROFILES[x["producer_id"]]["country"] for x in s}
    assert {"Colombia", "Mexico", "Vietnam"} <= countries, "the vision doc's three scenarios"
    # The web picker and the demo sign-in allow-list read the top level, so only S1 to S7 live there
    assert sorted((EVAL / "scenarios").glob("*.json")) == SCENARIOS


def test_scenario_producers_match_the_producer_definitions():
    # #7 lists each scenario's producer once; the scenario files must agree with it
    assert {_load(p)["scenario_id"]: _load(p)["producer_id"] for p in SCENARIOS} == DEFINITIONS["scenario_producers"]


def test_every_contrast_pair_producer_has_a_scenario_run():
    run_producers = {_load(p)["producer_id"] for p in RUNS}
    for pair in DEFINITIONS["contrast_pairs"]:
        assert set(pair["producers"]) <= run_producers, pair["pair_id"]
    for path in CONTRAST:
        pair_id = path.stem.split("-", 1)[0]
        pair = next(p for p in DEFINITIONS["contrast_pairs"] if p["pair_id"] == pair_id)
        assert _load(path)["producer_id"] in pair["producers"], path.name


@pytest.mark.parametrize("path", RUNS, ids=[p.stem for p in RUNS])
def test_scenario_is_well_formed(path):
    s = _load(path)
    assert s["scenario_id"] == path.stem
    assert s["producer_id"] in PROFILES, "must be in the producer table (#7), so the tools have data"
    assert s["language"] in {"en", "es"}
    assert isinstance(s["intake_replies"], list)
    for reply in s["intake_replies"]:
        assert 1 <= len(reply) <= 4000
    turns = s["turns"]
    assert turns and "action" in turns[-1] and turns[-1]["action"]["name"] == "end", "the last turn is always end"
    for t in turns:
        assert ("message" in t) ^ ("action" in t), "a turn is a message or an action, not both"
        assert t["expect_step"] in STEPS, t["expect_step"]
        blob = json.dumps(t).lower()
        assert "producer_id" not in blob and "producerid" not in blob
        if "message" in t:
            assert 1 <= len(t["message"]) <= 4000
        else:
            name, args = t["action"]["name"], t["action"]["args"]
            assert name in ACTIONS, name
            assert set(args) == set(ACTIONS[name]), (name, args)
            for key, allowed in ACTIONS[name].items():
                if allowed:
                    assert args[key] in allowed, (name, args)
    exp = s["expected"]
    assert exp["tags"] and set(exp["tags"]) <= TAGS
    assert exp["evidence"] in {"full", "limited"}
    assert exp["record_status"] in {"completed", "declined"}
    assert isinstance(exp["pii_flag"], bool)
    assert set(exp["pii_entity_types"]) <= PII_TYPES
    if exp["pii_flag"]:
        assert exp["pii_entity_types"], "a flagged record names the entity types it was flagged for"
    assert isinstance(exp["out_of_scope"], bool)


@pytest.mark.parametrize("path", RUNS, ids=[p.stem for p in RUNS])
def test_each_turn_expects_the_step_it_lands_in(path):
    """The runner checks expect_step against the turn's response stream, so it is the step the turn ends in:
    each action must be allowed in the step the previous turn ended in, and the closing `end` ends in closed."""
    step = "intake"
    for t in _load(path)["turns"]:
        if "action" in t:
            assert t["action"]["name"] in ALLOWED[step], (step, t["action"]["name"])
        step = t["expect_step"]
    assert step == "closed"


@pytest.mark.parametrize("path", RUNS, ids=[p.stem for p in RUNS])
def test_expected_record_matches_the_last_choices(path):
    s = _load(path)
    actions = [t["action"] for t in s["turns"] if "action" in t]
    consent = [a["args"]["scope"] for a in actions if a["name"] == "set_consent"]
    exp = s["expected"]
    assert consent, "every scenario grants or declines consent before it ends"
    assert exp["consent_scope"] == consent[-1]
    assert exp["record_status"] == ("declined" if consent[-1] == "declined" else "completed")


def test_labeled_set_covers_every_tag():
    used = {tag for item in LABELS for tag in item["reference"]}
    assert used == TAGS
    for tag in TAGS:
        assert sum(tag in item["reference"] for item in LABELS) >= 2, tag


def test_labeled_items_are_well_formed():
    assert len(LABELS) == 15, "the decided minimum set is fifteen accounts"
    ids = [item["id"] for item in LABELS]
    assert len(ids) == len(set(ids))
    for item in LABELS:
        assert item["language"] in {"en", "es"} and item["text"].strip()
        assert item["producer_id"] in PROFILES, "each account is a real sample producer"
        assert item["reference"] and set(item["reference"]) <= TAGS
        assert set(item["labeler_a"]) <= TAGS and set(item["labeler_b"]) <= TAGS
    assert {item["language"] for item in LABELS} == {"en", "es"}
