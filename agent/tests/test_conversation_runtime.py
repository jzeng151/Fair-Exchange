"""Issue #13: the AgentCore entrypoint passes requests to the engine and returns its events as JSON."""
from tests.conversation_harness import Run, intake

from fex.conversation import runtime


def test_model_ids_are_configuration(monkeypatch):
    monkeypatch.setenv("FEX_SMALL_MODEL", "us.anthropic.small-test")
    monkeypatch.setenv("FEX_LARGE_MODEL", "us.anthropic.large-test")
    small, large = runtime.model_ids()
    assert (small, large) == ("us.anthropic.small-test", "us.anthropic.large-test")


def test_default_models_use_us_inference_profiles(monkeypatch):
    monkeypatch.delenv("FEX_SMALL_MODEL", raising=False)
    monkeypatch.delenv("FEX_LARGE_MODEL", raising=False)
    assert all(m.startswith("us.anthropic.") for m in runtime.model_ids())


def test_invoke_returns_events_as_plain_json():
    r = Run()
    r.small.add(intake("¿Qué ha sido difícil?"))
    out = runtime.invoke({"kind": "start", "producerId": r.producer_id, "conversationId": "c1"}, engine=r.engine)
    assert out["events"][-1] == {"type": "done", "seq": len(out["events"])}
    assert any(e["type"] == "text" for e in out["events"])


def test_invoke_returns_resume_as_plain_json():
    r = Run()
    r.small.add(intake("Hola"))
    runtime.invoke({"kind": "start", "producerId": r.producer_id, "conversationId": "c1"}, engine=r.engine)
    out = runtime.invoke({"kind": "resume", "producerId": r.producer_id, "conversationId": "c1"}, engine=r.engine)
    assert out["resume"]["step"] == "intake" and out["resume"]["allowed"] == ["end"]


def test_invoke_rejects_a_malformed_request_without_raising():
    out = runtime.invoke({"kind": "action", "producerId": "P", "conversationId": "c",
                          "action": {"name": "set_consent", "args": {"scope": "everyone"}}}, engine=Run().engine)
    assert out["error"]["code"] == "invalid_request"


def test_stream_yields_every_event_in_order():
    # Incremental delivery itself is proven deterministically at the engine level
    # (test_events_are_delivered_as_they_happen_not_after_the_turn); here: the runtime passes each one on.
    r = Run()
    r.to_playback()
    r.small.add(("out", "RecordSummary", {"summary_original": "x", "summary_english": "x", "tags": ["water"]}))
    received = []
    from tests.conversation_harness import RETRIEVE
    r.large.add(*RETRIEVE, r.good_answer())
    for event in runtime.stream({"kind": "action", "producerId": r.producer_id, "conversationId": r.conversation_id,
                                 "action": {"name": "confirm_playback", "args": {}}}, engine=r.engine):
        received.append(event)
    assert received[-1]["type"] == "done"
    assert [e["seq"] for e in received] == list(range(1, len(received) + 1))
    assert any(e["type"] == "claim" for e in received)


def test_stream_turns_a_malformed_request_into_one_error_item():
    out = list(runtime.stream({"kind": "message", "producerId": "P", "conversationId": "c", "text": ""},
                              engine=Run().engine))
    assert out == [{"error": {"code": "invalid_request", "message": out[0]["error"]["message"]}}]


def test_stream_returns_resume_as_one_item():
    r = Run()
    r.small.add(intake("Hola"))
    runtime.invoke({"kind": "start", "producerId": r.producer_id, "conversationId": "c1"}, engine=r.engine)
    out = list(runtime.stream({"kind": "resume", "producerId": r.producer_id, "conversationId": "c1"}, engine=r.engine))
    assert len(out) == 1 and out[0]["resume"]["step"] == "intake"
