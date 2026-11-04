"""PII flagging (#20), Seam 1 (agent entrypoint) with a stub Comprehend client.

Spec: docs/specs/20-pii-flagging.md. Comprehend DetectPiiEntities scans the producer's own text at each
save, in English and Spanish, for NAME/PHONE/EMAIL/ADDRESS above a threshold. Nothing is redacted; a failed
or unsupported check flags the record too, and a flag never regresses to clean.
"""
import logging

import boto3
import pytest
from moto import mock_aws

from fex.pii import PiiScanner
from fex.records import DynamoRecordStore
from tests.conversation_harness import Run

TABLE = "fair-exchange-records-pii-test"


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        yield ddb.create_table(
            TableName=TABLE, KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST")


class StubComprehend:
    """A fake Comprehend client. `entities` maps a substring to (Type, Score); a hit is returned when the
    producer's text contains that substring. `fail_on` substrings raise, like a Comprehend error. Records the
    language of every call."""

    def __init__(self, entities=None, fail_on=(), score=0.99):
        self.entities = entities or {}
        self.fail_on = tuple(fail_on)
        self.score = score
        self.calls: list[tuple[str, str]] = []  # (text, language)

    def detect_pii_entities(self, Text: str, LanguageCode: str):  # noqa: N803 - boto3 param names
        self.calls.append((Text, LanguageCode))
        if any(bad in Text for bad in self.fail_on):
            raise RuntimeError("comprehend boom")
        found = []
        for needle, spec in self.entities.items():
            start = Text.find(needle)
            if start >= 0:
                kind, score = (spec, self.score) if isinstance(spec, str) else spec
                found.append({"Type": kind, "Score": score,
                              "BeginOffset": start, "EndOffset": start + len(needle)})
        return {"Entities": found}


def scanner(stub, threshold=0.8):
    return PiiScanner(stub, threshold=threshold)


def completed_run(table, stub, language="es", first_message=None):
    """A conversation driven to the consent step with a records store and a PII scanner."""
    run = Run(records=DynamoRecordStore(table), pii_scanner=scanner(stub))
    run.small.add(("out", "IntakeTurn", {"reply": "¿Qué pasó?", "ready_for_playback": False, "language": language}),
                  ("out", "IntakeTurn", {"reply": "", "ready_for_playback": True, "language": language}),
                  _playback(language))
    run.send("start")
    run.send("message", text=first_message or _default_message(language))
    run.small.add(_summary(language))
    from tests.conversation_harness import RETRIEVE
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    return run


def _default_message(language):
    return "La lluvia bajó mucho." if language == "es" else "The rain fell a lot."


def _playback(language):
    text = "Entiendo." if language == "es" else "I understand."
    return ("out", "PlaybackDraft", {"text": text, "challenge": "x", "timing": "x", "severity": "x",
                                     "tried": "x", "entity_type": None, "location_disputed": False})


def _summary(language):
    return ("out", "RecordSummary", {"summary_original": "x", "summary_english": "Rain fell.",
                                     "tags": ["water"]})


def record(run, table):
    items = [i for i in table.scan()["Items"] if i["record_id"] == run.conversation_id]
    assert len(items) == 1
    return items[0]


# ---------------------------------------------------------------- flagging

def test_a_name_in_a_spanish_message_flags_the_record_with_name(table):
    stub = StubComprehend(entities={"María López": "NAME"})
    run = completed_run(table, stub, first_message="Mi vecina María López también sufrió.")
    run.action("set_consent", scope="internal")
    rec = record(run, table)
    assert rec["pii_flag"] is True
    assert rec["pii_entity_types"] == ["NAME"]
    assert rec["pii_check"] == "done"
    assert len(rec["pii_matches"]) == 1
    assert rec["pii_matches"][0]["text"] == "María López"
    assert "María López" in rec["pii_matches"][0]["context"]
    assert rec["pii_matches"][0]["entity_type"] == "NAME"
    assert all(lang == "es" for _, lang in stub.calls)


def test_a_low_confidence_address_below_the_threshold_does_not_flag(table):
    # "Cauca" read as ADDRESS at 0.6, below the 0.8 threshold
    stub = StubComprehend(entities={"Cauca": ("ADDRESS", 0.6)})
    run = completed_run(table, stub, first_message="Vivo en Cauca.")
    run.action("set_consent", scope="internal")
    rec = record(run, table)
    assert rec["pii_flag"] is False
    assert rec["pii_entity_types"] == []
    assert rec["pii_matches"] == []
    assert rec["pii_check"] == "done"


def test_a_comprehend_error_flags_with_failed(table):
    stub = StubComprehend(fail_on=["La lluvia"])
    run = completed_run(table, stub)
    run.action("set_consent", scope="internal")
    rec = record(run, table)
    assert rec["pii_flag"] is True
    assert rec["pii_check"] == "failed"
    assert rec["pii_matches"] == []


def test_a_non_supported_language_flags_with_unsupported_language(table):
    stub = StubComprehend(entities={"anyone": "NAME"})
    run = completed_run(table, stub, language="fr", first_message="Il a peu plu cette saison.")
    run.action("set_consent", scope="internal")
    rec = record(run, table)
    assert rec["pii_check"] == "unsupported_language"
    assert rec["pii_flag"] is True
    assert stub.calls == []  # Comprehend is never called for an unsupported language


def test_a_failed_text_is_rescanned_and_pii_check_stays_failed_until_it_succeeds(table):
    stub = StubComprehend(fail_on=["La lluvia"])
    run = completed_run(table, stub)
    run.action("set_consent", scope="internal")
    assert record(run, table)["pii_check"] == "failed"
    # Comprehend recovers; the next save rescans the previously failed text
    stub.fail_on = ()
    run.action("set_feedback", value="yes")
    rec = record(run, table)
    assert rec["pii_check"] == "done"
    assert rec["pii_flag"] is True  # the flag set by the failure stays set


def test_correct_playback_text_is_scanned(table):
    stub = StubComprehend(entities={"Juan Pérez": "NAME"})
    run = Run(records=DynamoRecordStore(table), pii_scanner=scanner(stub))
    run.small.add(("out", "IntakeTurn", {"reply": "¿Qué pasó?", "ready_for_playback": False, "language": "es"}),
                  ("out", "IntakeTurn", {"reply": "", "ready_for_playback": True, "language": "es"}),
                  _playback("es"), _playback("es"), _summary("es"))
    run.send("start")
    run.send("message", text="La lluvia bajó.")
    run.action("correct_playback", text="También mi socio Juan Pérez perdió la cosecha.")
    from tests.conversation_harness import RETRIEVE
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    run.action("set_consent", scope="internal")
    rec = record(run, table)
    assert rec["pii_entity_types"] == ["NAME"]
    assert rec["pii_matches"][0]["text"] == "Juan Pérez"


def test_texts_marked_done_are_not_scanned_again(table):
    stub = StubComprehend(entities={"María López": "NAME"})
    run = completed_run(table, stub, first_message="Mi vecina María López también sufrió.")
    run.action("set_consent", scope="internal")
    calls_after_first_save = len(stub.calls)
    run.action("set_feedback", value="yes")
    run.action("end")
    assert len(stub.calls) == calls_after_first_save  # the one producer text was scanned once


def test_no_producer_text_is_altered(table):
    stub = StubComprehend(entities={"María López": "NAME"})
    message = "Mi vecina María López también sufrió."
    run = completed_run(table, stub, first_message=message)
    run.action("set_consent", scope="internal")
    producer_texts = [e.text for e in run.state().history if getattr(e, "role", None) == "producer"]
    assert message in producer_texts  # kept exactly as written; nothing redacted


# ---------------------------------------------------------------- out of scope and declined

def test_out_of_scope_message_contributes_nothing_to_the_pii_fields(table):
    """A grievance naming a worker (out of scope), then an in-scope challenge: the record's PII fields
    contain nothing from the grievance."""
    from fex.conversation.scope import ScopeVerdict

    def scope_check(text, step):
        if "despidieron" in text:  # the grievance
            return ScopeVerdict(in_scope=False, reason="other_producer_data")
        return ScopeVerdict(in_scope=True)

    stub = StubComprehend(entities={"Pedro Gómez": "NAME", "María López": "NAME"})
    run = Run(records=DynamoRecordStore(table), pii_scanner=scanner(stub), scope_check=scope_check)
    run.small.add(("out", "IntakeTurn", {"reply": "¿Qué pasó?", "ready_for_playback": False, "language": "es"}),
                  ("out", "IntakeTurn", {"reply": "", "ready_for_playback": True, "language": "es"}),
                  _playback("es"), _summary("es"))
    run.send("start")
    run.send("message", text="A Pedro Gómez lo despidieron injustamente.")  # out of scope, names a worker
    run.send("message", text="Mi vecina María López y yo perdimos la cosecha por la lluvia.")  # in scope
    from tests.conversation_harness import RETRIEVE
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    run.action("set_consent", scope="internal")
    rec = record(run, table)
    texts = [m["text"] for m in rec["pii_matches"]]
    assert "María López" in texts
    assert "Pedro Gómez" not in texts  # nothing from the out-of-scope grievance
    assert all("Pedro" not in m["context"] for m in rec["pii_matches"])
    assert all("Pedro Gómez" not in text for text, _ in stub.calls)  # the grievance was never scanned


def test_pii_matches_are_removed_when_consent_changes_to_declined(table):
    stub = StubComprehend(entities={"María López": "NAME"})
    run = completed_run(table, stub, first_message="Mi vecina María López también sufrió.")
    run.action("set_consent", scope="internal")
    assert record(run, table)["pii_matches"]  # flagged while completed
    run.action("set_consent", scope="declined")
    rec = record(run, table)
    assert rec["status"] == "declined"
    assert "pii_matches" not in rec
    assert "pii_entity_types" not in rec
    assert "pii_flag" not in rec


# ---------------------------------------------------------------- logging

def test_logs_hold_no_matched_text(table, caplog):
    stub = StubComprehend(entities={"María López": "NAME"})
    with caplog.at_level(logging.DEBUG, logger="fex"):
        run = completed_run(table, stub, first_message="Mi vecina María López también sufrió.")
        run.action("set_consent", scope="internal")
    assert "María López" not in caplog.text
