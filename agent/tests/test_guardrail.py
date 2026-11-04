"""Issue #12: Bedrock Guardrail in detect mode. Spec: docs/specs/12-guardrail.md.

Seam 1 (agent entrypoint) with a model stub returning a Guardrail trace, the way Bedrock returns it in the
stream's `metadata` event. The finding is logged without text, nothing reaches the record, and the
conversation continues unchanged.
"""
import json
import logging

import boto3
import pytest
from moto import mock_aws
from tests.conversation_harness import Run, intake, of

from fex.conversation import runtime
from fex.conversation.guardrail import findings
from fex.records import DynamoRecordStore

SECRET = "Quiero saber el resultado de la auditoría de certificación"

# A detect-mode assessment: action NONE, detected true. Bedrock can include matched text in some policies
# (e.g. word or PII matches); none of it may be logged.
TRACE = {
    "inputAssessment": {
        "gr-123": {
            "topicPolicy": {"topics": [{"name": "Certification status and audit results", "type": "DENY",
                                        "action": "NONE", "detected": True}]},
            "contentPolicy": {"filters": [{"type": "INSULTS", "confidence": "LOW", "action": "NONE",
                                           "detected": False}]},
            "wordPolicy": {"customWords": [{"match": SECRET, "action": "NONE", "detected": True}]},
        }
    },
    "outputAssessments": {
        "gr-123": [{"contentPolicy": {"filters": [{"type": "MISCONDUCT", "confidence": "MEDIUM",
                                                    "action": "NONE", "detected": True}]}}]
    },
}


def test_findings_list_policy_and_topic_or_category_only():
    assert findings(TRACE) == [
        {"source": "input", "policy": "topicPolicy", "name": "Certification status and audit results"},
        {"source": "input", "policy": "wordPolicy", "name": "customWords"},
        {"source": "output", "policy": "contentPolicy", "name": "MISCONDUCT"},
    ]
    assert SECRET not in json.dumps(findings(TRACE))


def test_undetected_items_are_not_findings():
    quiet = {"inputAssessment": {"g": {"contentPolicy": {"filters": [{"type": "HATE", "action": "NONE",
                                                                       "detected": False}]}}}}
    assert findings(quiet) == []
    assert findings({}) == [] and findings(None) == []


def test_a_guardrail_finding_is_logged_with_the_conversation_id_and_no_text(caplog):
    r = Run()
    r.small.add(intake("¿Qué ha sido difícil?"))
    r.send("start")
    r.small.guardrail_traces.append(TRACE)
    r.small.add(intake("¿Desde cuándo pasa?"))
    with caplog.at_level(logging.INFO, logger="fex.guardrail"):
        events = r.send("message", text=SECRET)
    logged = [json.loads(rec.getMessage()) for rec in caplog.records if rec.name == "fex.guardrail"]
    assert {"conversation_id": r.conversation_id, "source": "input", "policy": "topicPolicy",
            "name": "Certification status and audit results"} in logged
    everything = " ".join(rec.getMessage() for rec in caplog.records)
    assert SECRET not in everything and "auditoría" not in everything
    # the conversation continues unchanged
    assert r.state().step == "intake" and "¿Desde cuándo pasa?" in "".join(e.text for e in of(events, "text"))


def test_a_guardrail_finding_never_reaches_the_record():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        table = ddb.create_table(TableName="t", KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                                 AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                                 BillingMode="PAY_PER_REQUEST")
        r = Run(records=DynamoRecordStore(table))
        r.small.guardrail_traces.extend([TRACE] * 3)
        r.large.guardrail_traces.extend([TRACE] * 3)
        r.to_consent()
        r.action("set_consent", scope="internal")
        item = json.dumps(table.scan()["Items"], default=str)
        assert "guardrail" not in item.lower() and "Certification status" not in item and "MISCONDUCT" not in item


def test_guardrail_findings_from_the_answer_model_are_logged_too(caplog):
    r = Run()
    r.to_playback()
    from tests.conversation_harness import RETRIEVE, summary
    r.small.add(summary())
    r.large.guardrail_traces.extend([None, None, TRACE])  # on the call that writes the answer
    r.large.add(*RETRIEVE, r.good_answer())
    with caplog.at_level(logging.INFO, logger="fex.guardrail"):
        r.action("confirm_playback")
    assert any(json.loads(rec.getMessage())["name"] == "MISCONDUCT"
               for rec in caplog.records if rec.name == "fex.guardrail")


# ---------------------------------------------------------------- attachment (runtime configuration)

def test_every_model_gets_the_guardrail_with_trace_on_and_redaction_off(monkeypatch):
    monkeypatch.setenv("FEX_GUARDRAIL_ID", "gr-123")
    monkeypatch.setenv("FEX_GUARDRAIL_VERSION", "1")
    assert runtime.guardrail_config() == {
        "guardrail_id": "gr-123", "guardrail_version": "1", "guardrail_trace": "enabled",
        "guardrail_redact_input": False, "guardrail_redact_output": False,
    }


def test_no_guardrail_when_it_is_not_configured(monkeypatch):
    monkeypatch.delenv("FEX_GUARDRAIL_ID", raising=False)
    monkeypatch.delenv("FEX_GUARDRAIL_VERSION", raising=False)
    assert runtime.guardrail_config() == {}


@pytest.mark.parametrize("missing", ["FEX_GUARDRAIL_ID", "FEX_GUARDRAIL_VERSION"])
def test_a_half_configured_guardrail_is_an_error(monkeypatch, missing):
    monkeypatch.setenv("FEX_GUARDRAIL_ID", "gr-123")
    monkeypatch.setenv("FEX_GUARDRAIL_VERSION", "1")
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError):
        runtime.guardrail_config()


# ---------------------------------------------------------------- review fix (Codex on #80)

@pytest.fixture
def default_logging():
    """The guardrail logger exactly as Python leaves it: no level, no handler (no test-only override)."""
    lg = logging.getLogger("fex.guardrail")
    saved = (lg.level, list(lg.handlers), lg.propagate)
    lg.setLevel(logging.NOTSET)
    lg.handlers.clear()
    lg.propagate = True
    yield lg
    lg.setLevel(saved[0])
    lg.handlers[:] = saved[1]
    lg.propagate = saved[2]


def test_runtime_logging_writes_findings_to_stdout_for_cloudwatch(default_logging, capsys):
    from fex.conversation.guardrail import log_findings
    runtime.configure_logging()
    log_findings(TRACE, "conv-9")
    out = capsys.readouterr().out
    assert '"conversation_id": "conv-9"' in out and "Certification status and audit results" in out
    assert SECRET not in out


def test_configuring_logging_twice_adds_one_handler(default_logging):
    runtime.configure_logging()
    runtime.configure_logging()
    assert len(default_logging.handlers) == 1
