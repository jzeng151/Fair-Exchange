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


def test_records_are_saved_only_when_a_table_is_configured(monkeypatch):
    monkeypatch.delenv("FEX_RECORDS_TABLE", raising=False)
    assert runtime.record_store() is None
    monkeypatch.setenv("FEX_RECORDS_TABLE", "fair-exchange-records")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    store = runtime.record_store()
    assert store is not None and store.table.name == "fair-exchange-records"
