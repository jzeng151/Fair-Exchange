"""The standards KB ingestion custom resource (#17, infra/lib/standards-kb/ingest_handler.py).

Ingestion failure or timeout must fail the deploy; delete does nothing. AWS clients and the
CloudFormation response URL are faked; the handler file is loaded exactly as the Lambda inlines it.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

HANDLER = Path(__file__).resolve().parents[2] / "infra" / "lib" / "standards-kb" / "ingest_handler.py"


class FakeBedrockAgent:
    def __init__(self):
        self.started, self.stopped, self.status, self.stats, self.reasons = [], [], "IN_PROGRESS", {}, []

    def start_ingestion_job(self, **kw):
        self.started.append(kw)
        return {"ingestionJob": {"ingestionJobId": "JOB1"}}

    def get_ingestion_job(self, **kw):
        return {"ingestionJob": {"status": self.status, "statistics": self.stats, "failureReasons": self.reasons}}

    def stop_ingestion_job(self, **kw):
        self.stopped.append(kw)


class FakeStepFunctions:
    def __init__(self):
        self.executions = []

    def start_execution(self, **kw):
        self.executions.append(json.loads(kw["input"]))


@pytest.fixture
def handler(monkeypatch):
    agent, sfn, responses = FakeBedrockAgent(), FakeStepFunctions(), []
    fake_boto3 = types.SimpleNamespace(client=lambda name: {"bedrock-agent": agent, "stepfunctions": sfn}[name])
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:us-west-2:1:stateMachine:x")
    monkeypatch.setenv("LIMIT_SECONDS", "1200")
    spec = importlib.util.spec_from_file_location("ingest_handler", HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.urllib.request, "urlopen",
                        lambda req, timeout: responses.append(json.loads(req.data)))
    return types.SimpleNamespace(module=module, agent=agent, sfn=sfn, responses=responses)


def cfn_event(kind="Create", **extra):
    return {"RequestType": kind, "ResponseURL": "https://example.invalid/r", "StackId": "s", "RequestId": "r",
            "LogicalResourceId": "IngestClauses",
            "ResourceProperties": {"KnowledgeBaseId": "KB", "DataSourceId": "DS", "ContentHash": "h"}, **extra}


def started(h):
    h.module.handler(cfn_event(), None)
    return h.sfn.executions[0]


def test_create_starts_ingestion_and_the_poll_loop_without_answering_yet(handler):
    state = started(handler)
    assert handler.agent.started == [{"knowledgeBaseId": "KB", "dataSourceId": "DS"}]
    assert state["job"] == "JOB1" and state["done"] is False
    assert handler.responses == []


def test_update_with_a_new_hash_re_ingests(handler):
    handler.module.handler(cfn_event("Update", PhysicalResourceId="KB/DS"), None)
    assert len(handler.agent.started) == 1 and handler.sfn.executions[0]["cfn"]["PhysicalResourceId"] == "KB/DS"


def test_delete_does_nothing_and_succeeds(handler):
    handler.module.handler(cfn_event("Delete", PhysicalResourceId="KB/DS"), None)
    assert handler.agent.started == [] and [r["Status"] for r in handler.responses] == ["SUCCESS"]


def test_in_progress_keeps_polling(handler):
    assert handler.module.handler(started(handler), None)["done"] is False
    assert handler.responses == []


def test_completed_ingestion_succeeds(handler):
    state = started(handler)
    handler.agent.status, handler.agent.stats = "COMPLETE", {"numberOfNewDocumentsIndexed": 700}
    assert handler.module.handler(state, None)["done"] is True
    assert handler.responses[0]["Status"] == "SUCCESS" and handler.responses[0]["PhysicalResourceId"] == "KB/DS"


def test_failed_documents_fail_the_deploy(handler):
    state = started(handler)
    handler.agent.status, handler.agent.stats = "COMPLETE", {"numberOfDocumentsFailed": 3}
    handler.module.handler(state, None)
    assert handler.responses[0]["Status"] == "FAILED" and "3 documents failed" in handler.responses[0]["Reason"]


def test_a_failed_job_fails_the_deploy(handler):
    state = started(handler)
    handler.agent.status, handler.agent.reasons = "FAILED", ["AccessDenied on index"]
    handler.module.handler(state, None)
    assert handler.responses[0]["Status"] == "FAILED" and "AccessDenied" in handler.responses[0]["Reason"]


def test_past_the_time_limit_stops_the_job_and_fails_the_deploy(handler):
    state = {**started(handler), "deadline": 0}
    assert handler.module.handler(state, None)["done"] is True
    assert handler.agent.stopped and handler.responses[0]["Status"] == "FAILED"


def test_a_caught_poll_error_fails_the_deploy(handler):
    state = {**started(handler), "error": {"Error": "Lambda.Unknown", "Cause": "boom"}}
    handler.module.handler(state, None)
    assert handler.responses[0]["Status"] == "FAILED" and "boom" in handler.responses[0]["Reason"]


def test_a_start_failure_fails_the_deploy_at_once(handler):
    def refuse(**_):
        raise RuntimeError("ValidationException")
    handler.agent.start_ingestion_job = refuse
    handler.module.handler(cfn_event(), None)
    assert handler.sfn.executions == [] and handler.responses[0]["Status"] == "FAILED"
