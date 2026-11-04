"""Issue #101: a deterministic demo model, so the real engine runs end to end with no AWS and no cost.

These tests drive the REAL engine (real tools, real citation verifier, real record saving) with DemoModel,
not the scripted test harness: what passes here is what the local demo shows.
"""
import json

from fx_data.peers import ProducerProfiles
from fx_data.standards import Standards

from fex.conversation import ConversationEngine, InMemoryStateStore
from fex.conversation.demo_model import DemoModel
from fex.models import parse_record
from fex.records.local import FileRecordStore
from fex.tools.standards import LocalClauseRetriever

SPANISH = ["La lluvia ha bajado mucho y la cosecha de café cayó este año.",
           "Empezó hace dos temporadas.", "Es grave, perdimos casi la mitad.",
           "Probamos con abono, pero no alcanzó."]
ENGLISH = ["Coffee prices have dropped and members can't cover costs.", "Since last year.",
           "Serious, many members are leaving.", "We tried selling to a new buyer."]


def cauca() -> str:
    return next(pid for pid, p in ProducerProfiles.load()._profiles.items() if p["region"] == "Cauca")


def engine(tmp_path, model=None):
    model = model or DemoModel()
    return ConversationEngine(store=InMemoryStateStore(), small_model=model, large_model=model,
                              records=FileRecordStore(tmp_path), retriever=LocalClauseRetriever())


def talk(eng, producer, conversation, messages):
    req = {"producerId": producer, "conversationId": conversation}
    turns = [eng.handle({**req, "kind": "start"})]
    for text in messages:
        turns.append(eng.handle({**req, "kind": "message", "text": text}))
    turns.append(eng.handle({**req, "kind": "action", "action": {"name": "confirm_playback", "args": {}}}))
    turns.append(eng.handle({**req, "kind": "action", "action": {"name": "set_consent", "args": {"scope": "internal"}}}))
    turns.append(eng.handle({**req, "kind": "action", "action": {"name": "set_feedback", "args": {"value": "yes"}}}))
    return turns


def kinds(turn):
    return [e.type for e in turn]


def test_a_spanish_conversation_runs_end_to_end_and_saves_a_valid_record(tmp_path):
    eng = engine(tmp_path)
    turns = talk(eng, cauca(), "conv-es", SPANISH)
    steps = [e.step for t in turns for e in t if e.type == "step"]
    assert steps[0] == "intake" and "playback" in steps and "respond" in steps and steps[-1] == "feedback"
    claims = [e for t in turns for e in t if e.type == "claim"]
    assert {c.section for c in claims} == {"insights", "peer_examples"}  # real tool data, both sections
    assert not [e for t in turns for e in t if e.type == "error"]
    record = parse_record(json.loads((tmp_path / "conv-es.json").read_text(encoding="utf-8")))
    assert record.status == "completed" and record.language == "es" and record.summary_english
    assert record.feedback == "yes" and record.evidence == "full"
    assert record.tags[0] == "climate and weather"  # from the challenge (rain), not from what was tried (fertilizer)


def test_every_claim_passes_the_real_citation_verifier(tmp_path):
    eng = engine(tmp_path)
    turns = talk(eng, cauca(), "conv-v", SPANISH)
    standards = Standards.load()
    for c in [e.claim for t in turns for e in t if e.type == "claim"]:
        assert standards.exists(c.citation.standard_clause), c.citation.standard_clause
    answer = [e for t in turns for e in t if e.type == "answer"][0]
    assert answer.insights and answer.peer_examples


def test_an_english_conversation_stays_in_english(tmp_path):
    eng = engine(tmp_path)
    talk(eng, cauca(), "conv-en", ENGLISH)
    record = parse_record(json.loads((tmp_path / "conv-en.json").read_text(encoding="utf-8")))
    assert record.language == "en" and record.summary_english is None
    assert "market and price" in record.tags


def test_the_demo_model_is_deterministic(tmp_path):
    a = [[e.model_dump() for e in t] for t in talk(engine(tmp_path / "a"), cauca(), "c", SPANISH)]
    b = [[e.model_dump() for e in t] for t in talk(engine(tmp_path / "b"), cauca(), "c", SPANISH)]
    assert a == b


def test_the_demo_model_follows_the_intake_questions_before_playing_back(tmp_path):
    eng = engine(tmp_path)
    req = {"producerId": cauca(), "conversationId": "c2"}
    eng.handle({**req, "kind": "start"})
    for text in SPANISH[:3]:
        eng.handle({**req, "kind": "message", "text": text})
        assert eng.store.load(cauca(), "c2").step == "intake"  # still asking timing, severity, what was tried
    eng.handle({**req, "kind": "message", "text": SPANISH[3]})
    assert eng.store.load(cauca(), "c2").step == "playback"
