"""Issue #21: out-of-scope handling (Journey 4). Spec: docs/specs/21-out-of-scope.md.

Seam 1 (agent entrypoint) with a FAKE detection function: how detection decides is "Not decided".
"""
import boto3
import pytest
from moto import mock_aws
from tests.conversation_harness import RETRIEVE, Run, intake, of, playback, summary

from fex.conversation.scope import ScopeVerdict, always_in_scope
from fex.records import DynamoRecordStore

MISDIRECTED = "Muéstreme los resultados de auditoría de la Cooperativa Vecina."


class FakeDetector:
    """Out of scope only for MISDIRECTED. Records every call it receives."""

    def __init__(self, reason="other_producer_data"):
        self.reason, self.calls = reason, []

    def __call__(self, text: str, step: str) -> ScopeVerdict:
        self.calls.append((text, step))
        if text == MISDIRECTED:
            return ScopeVerdict(in_scope=False, reason=self.reason)
        return ScopeVerdict(in_scope=True)


def spoken(events) -> str:
    return "".join(e.text for e in of(events, "text"))


def run_in(step: str, detector: FakeDetector, **kw) -> Run:
    r = Run(scope_check=detector, **kw)
    if step == "intake":
        r.small.add(intake("¿Qué ha sido difícil?"))
        r.send("start")
    elif step == "playback":
        r.to_playback()
    elif step == "consent":
        r.to_consent()
    elif step == "feedback":
        r.to_feedback()
    return r


@pytest.mark.parametrize("step", ["intake", "playback", "consent", "feedback"])
def test_out_of_scope_request_keeps_the_step_and_calls_no_model_or_tool(step):
    detector = FakeDetector()
    r = run_in(step, detector)
    small_calls, large_calls = len(r.small.calls), len(r.large.calls)
    events = r.send("message", text=MISDIRECTED)
    assert r.state().step == step
    assert (len(r.small.calls), len(r.large.calls)) == (small_calls, large_calls)  # no model, no data tool
    assert not of(events, "error")


@pytest.mark.parametrize("reason, words", [
    ("other_producer_data", "otros productores"),
    ("certification_status", "certificación"),
    ("grievance", "quejas"),
])
def test_decline_says_why_in_the_producers_language_and_offers_to_return(reason, words):
    r = run_in("intake", FakeDetector(reason))
    text = spoken(r.send("message", text=MISDIRECTED)).lower()
    assert words in text
    assert "¿qué ha sido difícil" in text  # back to the open question


def test_detection_gets_the_message_and_the_current_step():
    detector = FakeDetector()
    r = run_in("playback", detector)
    r.send("message", text=MISDIRECTED)
    assert detector.calls[-1] == (MISDIRECTED, "playback")


def test_out_of_scope_in_playback_is_not_treated_as_a_correction():
    r = run_in("playback", FakeDetector())
    before = r.state().playback.text
    r.send("message", text=MISDIRECTED)
    assert r.state().playback.text == before


def test_requests_for_peer_examples_are_in_scope():
    detector = FakeDetector()
    r = run_in("intake", detector)
    r.small.add(intake("¿Desde cuándo pasa?"))
    events = r.send("message", text="¿Qué hicieron otras cooperativas con la sequía?")
    assert "¿Desde cuándo pasa?" in spoken(events)
    assert r.state().step == "intake"


def test_the_misdirected_text_never_reaches_playback_or_summaries():
    r = run_in("intake", FakeDetector())
    r.send("message", text=MISDIRECTED)
    r.small.add(intake("", ready=True), playback())
    r.send("message", text="La lluvia bajó y la cosecha cayó.")
    r.small.add(summary())
    r.large.add(*RETRIEVE, r.good_answer())
    r.action("confirm_playback")
    assert all(MISDIRECTED not in prompt and "Vecina" not in prompt for prompt in r.small.prompts + r.large.prompts)


def test_the_record_contains_none_of_the_misdirected_text():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        table = ddb.create_table(TableName="t", KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                                 AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                                 BillingMode="PAY_PER_REQUEST")
        r = run_in("intake", FakeDetector(), records=DynamoRecordStore(table))
        r.send("message", text=MISDIRECTED)
        r.small.add(intake("", ready=True), playback())
        r.send("message", text="La lluvia bajó.")
        r.small.add(summary())
        r.large.add(*RETRIEVE, r.good_answer())
        r.action("confirm_playback")
        r.action("set_consent", scope="internal")
        item = table.scan()["Items"][0]
        assert "Vecina" not in str(item) and "auditoría" not in str(item)


def test_resume_history_still_shows_the_exchange():
    r = run_in("intake", FakeDetector())
    r.send("message", text=MISDIRECTED)
    texts = [h.text for h in r.send("resume").history if h.role in ("producer", "fex")]
    assert MISDIRECTED in texts


def test_the_default_detector_treats_everything_as_in_scope():
    assert always_in_scope("anything", "intake") == ScopeVerdict(in_scope=True)
