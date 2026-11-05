"""The real Strands classifier with a scripted model, exercised through its public callable."""
import pytest
from tests.conversation_harness import Run, ScriptedModel, intake, of, playback

from fex.conversation.scope import BedrockScopeCheck, ScopeUnavailable, ScopeVerdict


def classification(category="in_scope", language="en"):
    return ("out", "ScopeClassification", {"category": category, "language": language})


@pytest.mark.parametrize("category", ["in_scope", "certification_status", "grievance", "other_producer_data"])
@pytest.mark.parametrize("language", ["en", "es", "fr"])
def test_classification_returns_only_a_reason_and_language_without_data_tools(category, language):
    model = ScriptedModel([classification(category, language)])
    verdict = BedrockScopeCheck(model)("Synthetic message", "intake")
    assert verdict == ScopeVerdict(category == "in_scope", None if category == "in_scope" else category, language)
    assert model.calls and all(set(names) <= {"ScopeClassification"} for names in model.calls)


def test_provider_failure_is_safe_and_does_not_pass_the_message_through():
    check = BedrockScopeCheck(ScriptedModel([("raise", RuntimeError("private provider payload"))]))
    with pytest.raises(ScopeUnavailable, match="^Scope check unavailable$"):
        check("Synthetic sensitive message", "playback")


def test_invalid_classification_cannot_be_treated_as_in_scope():
    model = ScriptedModel([classification("made_up_category")])
    with pytest.raises(ScopeUnavailable):
        BedrockScopeCheck(model)("Synthetic message", "intake")


@pytest.mark.parametrize("correction", [False, True])
def test_failure_preserves_step_and_excludes_text_from_later_model_prompts(correction):
    r = Run()
    if correction:
        r.to_playback()
    else:
        r.small.add(intake("What has been difficult?")); r.send("start")
    before = r.state().step
    counts = len(r.small.calls), len(r.large.calls)
    model = ScriptedModel([("raise", RuntimeError("service unavailable")), classification()])
    r.engine.scope_check = BedrockScopeCheck(model)
    message = "Synthetic private classification failure marker"
    events = r.action("correct_playback", text=message) if correction else r.send("message", text=message)
    assert r.state().step == before
    assert (len(r.small.calls), len(r.large.calls)) == counts
    assert any("try" in e.text.lower() or "intente" in e.text.lower() for e in of(events, "text"))
    assert r.state().decision_log[-1].code == "scope_check_failed"
    r.small.add(playback() if correction else intake("When did it start?"))
    r.send("message", text="Our harvest fell last season.")
    assert all(message not in p for p in r.small.prompts + r.large.prompts)


def test_real_classifier_result_uses_fixed_french_refusal_without_answering_models():
    r = Run(scope_check=BedrockScopeCheck(ScriptedModel([classification("certification_status", "fr")])))
    r.small.add(intake("What has been difficult?")); r.send("start")
    counts = len(r.small.calls), len(r.large.calls)
    events = r.send("message", text="Mon certificat est-il toujours valide ?")
    assert (len(r.small.calls), len(r.large.calls)) == counts
    assert r.state().language == "fr" and r.state().step == "intake"
    assert "statut de certification" in "".join(e.text for e in of(events, "text"))
    assert r.state().decision_log[-1].code == "scope_declined_certification_status"


def test_live_runtime_wires_the_classifier_but_offline_demo_makes_no_aws_call(monkeypatch):
    from fex.conversation import runtime
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.delenv("FEX_DEMO_MODELS", raising=False)
    monkeypatch.delenv("FEX_RECORDS_TABLE", raising=False)
    monkeypatch.delenv("FEX_MEMORY_ID", raising=False)
    runtime.default_engine.cache_clear()
    try:
        assert isinstance(runtime.default_engine().scope_check, BedrockScopeCheck)
        runtime.default_engine.cache_clear()
        monkeypatch.setenv("FEX_DEMO_MODELS", "1")
        assert not isinstance(runtime.default_engine().scope_check, BedrockScopeCheck)
    finally:
        runtime.default_engine.cache_clear()
