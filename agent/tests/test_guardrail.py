"""Issue #12: Bedrock Guardrail in detect mode. Spec: docs/specs/12-guardrail.md.

Seam 1 (agent entrypoint) with scripted models that return a Guardrail trace in the stream's metadata
chunk, the way Bedrock's ConverseStream does. Findings are logged with no text, nothing reaches the
record, and the conversation is exactly what it would have been without the Guardrail.
"""
import json
import logging

import boto3
import pytest
from moto import mock_aws
from strands.models.bedrock import BedrockModel
from tests.conversation_harness import Run, ScriptedModel

from fex import guardrail
from fex.conversation import runtime
from fex.guardrail import GuardrailFindingsMixin, findings, guardrail_settings
from fex.records import DynamoRecordStore

PRODUCER_TEXT = "La lluvia bajó mucho y la cosecha cayó."
MODEL_TEXT = "SECRET MODEL OUTPUT"

# A detect-mode trace: every action is NONE. It carries text in modelOutput and in match fields,
# which must never be logged.
DENIED_TOPIC_TRACE = {
    "modelOutput": [MODEL_TEXT],
    "inputAssessment": {
        "gr-1": {
            "topicPolicy": {"topics": [{"name": "Certification status and audit results", "type": "DENY",
                                        "action": "NONE", "detected": True}]},
            "contentPolicy": {"filters": [
                {"type": "INSULTS", "confidence": "LOW", "action": "NONE", "detected": True},
                {"type": "HATE", "confidence": "NONE", "action": "NONE", "detected": False},
            ]},
            "wordPolicy": {"customWords": [{"match": PRODUCER_TEXT, "action": "NONE", "detected": True}],
                           "managedWordLists": [{"match": PRODUCER_TEXT, "type": "PROFANITY", "action": "NONE"}]},
        }
    },
    "outputAssessments": {
        "gr-1": [{"topicPolicy": {"topics": [{"name": "Worker grievances and complaints", "type": "DENY",
                                              "action": "NONE", "detected": True}]}}]
    },
}


class TracingScriptedModel(ScriptedModel):
    """A scripted model whose every call ends with a metadata chunk carrying `trace`, as Bedrock's does."""

    def __init__(self, trace=None):
        super().__init__()
        self.trace = trace
        self.invocation_states = []

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.invocation_states.append(dict(kwargs.get("invocation_state") or {}))
        async for chunk in super().stream(messages, tool_specs, system_prompt, **kwargs):
            yield chunk
        metadata = {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}
        if self.trace is not None:
            metadata["trace"] = {"guardrail": self.trace}
        yield {"metadata": metadata}


class GuardedScriptedModel(GuardrailFindingsMixin, TracingScriptedModel):
    """The same mixin the deployed GuardedBedrockModel uses, over a scripted model."""


def guarded_run(trace, records=None) -> Run:
    r = Run(records=records)
    r.small, r.large = GuardedScriptedModel(trace), GuardedScriptedModel(trace)
    r.engine.small_model, r.engine.large_model = r.small, r.large
    return r


def finding_logs(caplog) -> list[dict]:
    return [json.loads(rec.getMessage().split(" ", 1)[1]) for rec in caplog.records
            if rec.name == "fex.guardrail" and rec.getMessage().startswith("guardrail_finding ")]


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        yield ddb.create_table(TableName="fair-exchange-guardrail-test",
                               KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                               AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                               BillingMode="PAY_PER_REQUEST")


# ---------------------------------------------------------------- attachment


def test_settings_attach_the_guardrail_with_trace_on_and_redaction_off(monkeypatch):
    monkeypatch.setenv("FEX_GUARDRAIL_ID", "gr-abc")
    monkeypatch.setenv("FEX_GUARDRAIL_VERSION", "3")
    assert guardrail_settings() == {
        "guardrail_id": "gr-abc", "guardrail_version": "3", "guardrail_trace": "enabled",
        "guardrail_redact_input": False, "guardrail_redact_output": False,
    }


@pytest.mark.parametrize("missing", ["FEX_GUARDRAIL_ID", "FEX_GUARDRAIL_VERSION"])
def test_unconfigured_guardrail_is_reported_not_silent(monkeypatch, caplog, missing):
    monkeypatch.setenv("FEX_GUARDRAIL_ID", "gr-abc")
    monkeypatch.setenv("FEX_GUARDRAIL_VERSION", "3")
    monkeypatch.delenv(missing)
    with caplog.at_level(logging.WARNING, logger="fex.guardrail"):
        assert guardrail_settings() == {}
    assert "guardrail not configured" in caplog.text


def test_both_deployed_models_carry_the_guardrail(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("FEX_GUARDRAIL_ID", "gr-abc")
    monkeypatch.setenv("FEX_GUARDRAIL_VERSION", "3")
    monkeypatch.delenv("FEX_RECORDS_TABLE", raising=False)
    runtime.default_engine.cache_clear()
    try:
        engine = runtime.default_engine()
        for model in (engine.small_model, engine.large_model):
            assert isinstance(model, BedrockModel) and isinstance(model, GuardrailFindingsMixin)
            config = model.get_config()
            assert config["guardrail_id"] == "gr-abc" and config["guardrail_version"] == "3"
            assert config["guardrail_trace"] == "enabled"
            assert config["guardrail_redact_input"] is False and config["guardrail_redact_output"] is False
    finally:
        runtime.default_engine.cache_clear()


def test_every_model_call_carries_the_conversation_id():
    r = guarded_run(trace=None)
    r.to_feedback()
    assert r.small.invocation_states and r.large.invocation_states
    for state in r.small.invocation_states:
        assert state.get("conversation_id") == r.conversation_id
        # Small-model calls must not gain what the data tools need to run.
        assert "producer_id" not in state and "step" not in state
    for state in r.large.invocation_states:
        assert state["conversation_id"] == r.conversation_id and state["step"] == "respond"


# ---------------------------------------------------------------- findings


def test_findings_report_policy_and_category_without_text():
    found = findings(DENIED_TOPIC_TRACE)
    assert found == [
        {"source": "input", "policy": "topic", "category": "Certification status and audit results"},
        {"source": "input", "policy": "content", "category": "INSULTS"},
        {"source": "input", "policy": "word", "category": "PROFANITY"},
        {"source": "input", "policy": "word", "category": "custom_word"},
        {"source": "output", "policy": "topic", "category": "Worker grievances and complaints"},
    ]
    assert PRODUCER_TEXT not in json.dumps(found) and MODEL_TEXT not in json.dumps(found)


def test_empty_or_missing_traces_produce_no_findings():
    assert findings({}) == []
    assert findings({"inputAssessment": {"gr-1": {}}, "outputAssessments": {"gr-1": []}}) == []


def test_findings_are_logged_with_the_conversation_id_and_no_text(caplog):
    r = guarded_run(DENIED_TOPIC_TRACE)
    with caplog.at_level(logging.WARNING, logger="fex.guardrail"):
        r.to_playback()
    logged = finding_logs(caplog)
    assert logged, "expected Guardrail findings to be logged"
    assert {e["conversation_id"] for e in logged} == {r.conversation_id}
    assert {e["event"] for e in logged} == {"guardrail_finding"}
    assert {"policy": "topic", "category": "Certification status and audit results"}.items() <= logged[0].items()
    assert set(logged[0]) == {"event", "conversation_id", "source", "policy", "category"}
    all_logs = "\n".join(rec.getMessage() for rec in caplog.records)
    assert PRODUCER_TEXT not in all_logs and MODEL_TEXT not in all_logs


def test_a_logging_failure_never_breaks_the_conversation(monkeypatch, caplog):
    def broken(*_):
        raise RuntimeError("log sink down")

    monkeypatch.setattr(guardrail, "log_findings", broken)
    r = guarded_run(DENIED_TOPIC_TRACE)
    plain = Run()
    assert [e.model_dump() for e in r.to_playback()] == [e.model_dump() for e in plain.to_playback()]


# ---------------------------------------------------------------- no effect on the conversation or record


def test_findings_change_nothing_in_the_conversation_or_the_record(table):
    guarded = guarded_run(DENIED_TOPIC_TRACE, records=DynamoRecordStore(table))
    guarded_events = [e.model_dump() for e in guarded.to_feedback()]
    guarded_record = table.scan()["Items"]

    for item in guarded_record:
        table.delete_item(Key={"record_id": item["record_id"]})
    plain = Run(records=DynamoRecordStore(table))
    plain_events = [e.model_dump() for e in plain.to_feedback()]
    plain_record = table.scan()["Items"]

    assert guarded_events == plain_events
    assert guarded.state().model_dump() == plain.state().model_dump()
    assert guarded_record == plain_record and len(guarded_record) == 1
    # Nothing from the Guardrail is in the record in any form.
    record_text = json.dumps(guarded_record, default=str).lower()
    for marker in ("guardrail", "certification status and audit results", "insults", "worker grievances"):
        assert marker not in record_text
