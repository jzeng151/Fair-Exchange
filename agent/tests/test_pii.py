"""Issue #20: PII flagging. Comprehend seam-1 suite. The spec test list:
en/es scans flag on the four types, below-threshold and other types don't,
unsupported languages flag without scanning, failed calls flag, done texts are
never rescanned, out-of-scope texts add nothing, context +-10 words, the flag
persists once on, results apply to the record as-is, logs never carry matched text.
"""
import logging
from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_aws
from pydantic import ValidationError

from fex.conversation.contract import ActionEntry, SpokenEntry
from fex.conversation.state import ConversationState, Profile
from fex.models import CompletedRecord, DeclinedRecord, PiiMatch
from fex.pii import PiiText, context_window, scan_texts
from fex.records import DynamoRecordStore, producer_texts, run_pii_scan
from tests.conversation_harness import RETRIEVE, Run, intake, playback, summary

NOW = datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)
NAME_TEXT = "Mi nombre es María Torres y vivo en Popayán, la lluvia aquí es irregular."


def ent(kind: str, score: float, text: str, needle: str) -> dict:
    """An entity with Comprehend's response shape, pointing at `needle` in `text`."""
    begin = text.index(needle)
    return {"Type": kind, "Score": score, "BeginOffset": begin, "EndOffset": begin + len(needle)}


class SpyClient:
    """A Comprehend seam that records calls and can fail the n-th call.
    Entities are keyed by the text their offsets point into."""

    def __init__(self, entities: dict[str, list[dict]] | None = None, fail_on: int | None = None):
        self.entities = entities or {}
        self.fail_on = fail_on
        self.calls: list[str] = []

    def __call__(self, text: str, language: str) -> list[dict]:
        self.calls.append(text)
        if self.fail_on is not None and len(self.calls) == self.fail_on:
            raise RuntimeError("comprehend down")
        return list(self.entities.get(text, []))


def message(text: str, **overrides) -> PiiText:
    return PiiText(text=text, message_at=NOW, kind="message", **overrides)


def fixture_record(**overrides) -> dict:
    data = {
        "record_id": "R-0001", "producer_id": "258CC6A1", "status": "completed", "created_at": NOW,
        "updated_at": NOW, "version": 1, "evidence": "full",
        "consent": {"scope": "internal", "recorded_at": NOW},
        "language": "es", "entity_type": "cooperative",
        "summary_original": "La lluvia ha sido muy irregular y la cosecha bajó.",
        "summary_english": "Rainfall has been very irregular and the harvest dropped.",
        "tags": ["climate and weather"],
    }
    data.update(overrides)
    return data


def test_name_hit_flags_and_keeps_the_match():
    client = SpyClient({NAME_TEXT: [ent("PERSON", 0.99, NAME_TEXT, "María Torres")]})
    texts = [message(NAME_TEXT)]
    result = scan_texts(texts, "es", client)
    assert result.flag is True
    assert result.check == "done"
    assert result.entity_types == ["NAME"]
    match = result.matches[0]
    assert (match.entity_type, match.text, match.message_at) == ("NAME", "María Torres", NOW)
    assert "Popayán" in match.context
    assert texts[0].status == "done"


def test_phone_email_address_map_to_the_four_types():
    text = "Call 555-0102 or write maria@coop.org, the farm is on Route 3."
    client = SpyClient({text: [
        ent("PHONE_NUMBER", 0.97, text, "555-0102"),
        ent("EMAIL", 0.98, text, "maria@coop.org"),
        ent("ADDRESS", 0.9, text, "Route 3"),
    ]})
    result = scan_texts([message(text)], "en", client)
    assert result.entity_types == ["PHONE", "EMAIL", "ADDRESS"]


def test_below_threshold_does_not_flag():
    client = SpyClient({NAME_TEXT: [ent("PERSON", 0.3, NAME_TEXT, "María Torres")]})
    result = scan_texts([message(NAME_TEXT)], "es", client)
    assert result.flag is False
    assert result.check == "done"
    assert result.matches == [] and result.entity_types == []


def test_other_comprehend_types_are_ignored():
    client = SpyClient({NAME_TEXT: [ent("LOCATION", 0.99, NAME_TEXT, "Popayán")]})
    result = scan_texts([message(NAME_TEXT)], "es", client)
    assert result.flag is False
    assert result.entity_types == [] and result.matches == []


def test_unsupported_language_flags_without_scanning():
    # en/es/fr are supported (#24: fr through the Guardrail); any other language flags without scanning.
    client = SpyClient()
    texts = [message("Olá, a colheita está difícil.")]
    result = scan_texts(texts, "pt", client)
    assert result.flag is True
    assert result.check == "unsupported_language"
    assert client.calls == [] and result.matches == []
    assert texts[0].status == "pending"  # untouched: nothing was scanned


def test_failed_call_flags_and_marks_the_text_failed():
    client = SpyClient(fail_on=1)
    texts = [message(NAME_TEXT)]
    result = scan_texts(texts, "es", client)
    assert result.flag is True
    assert result.check == "failed"
    assert texts[0].status == "failed"
    assert result.matches == []  # a scan that did not run finds nothing


def test_failed_text_is_rescanned_and_done_never_is():
    client = SpyClient({NAME_TEXT: [ent("PERSON", 0.99, NAME_TEXT, "María Torres")]}, fail_on=1)
    texts = [message(NAME_TEXT), message("La cosecha bajó este año.")]
    first = scan_texts(texts, "es", client)
    assert first.check == "failed"
    assert client.calls == [NAME_TEXT, "La cosecha bajó este año."]  # pass 1 scans both pending texts

    second = scan_texts(texts, "es", client, prior_flag=first.flag,
                        prior_entity_types=first.entity_types, prior_matches=first.matches)
    assert client.calls == [NAME_TEXT, "La cosecha bajó este año.", NAME_TEXT]  # failed rescanned; done skipped
    assert second.check == "done"
    assert second.flag is True
    assert second.entity_types == ["NAME"]
    assert [m.text for m in second.matches] == ["María Torres"]


def test_out_of_scope_adds_nothing():
    grievance = "El supervisor Pablo Ruiz no nos pagó a tiempo."
    texts = [message(grievance, out_of_scope=True), message(NAME_TEXT)]
    client = SpyClient({NAME_TEXT: [ent("PERSON", 0.99, NAME_TEXT, "María Torres")]})
    result = scan_texts(texts, "es", client)
    assert client.calls == [NAME_TEXT]  # the grievance was never scanned
    assert texts[0].status == "pending"  # and no scan status touched it
    assert result.flag is True  # from the in-scope text only
    assert all(m.entity_type == "NAME" and m.text == "María Torres" for m in result.matches)
    assert not any("Pablo" in m.context or "Ruiz" in m.context for m in result.matches)


def test_context_keeps_ten_words_each_side():
    words = [f"w{i}" for i in range(1, 13)] + ["María", "Torres"] + [f"w{i}" for i in range(13, 25)]
    text = " ".join(words)
    begin, end = text.index("María"), text.index("Torres") + len("Torres")
    result = scan_texts([message(text)], "es", SpyClient({text: [ent("NAME", 0.99, text, "María Torres")]}))
    assert result.matches[0].context == " ".join(words[2:24])  # 10 before, match, 10 after, whole words


def test_short_context_stays_inside_the_text():
    result_text = "María Torres vive aquí."
    got = context_window(result_text, 0, len("María Torres"))
    assert got == result_text


def test_flag_persists_once_set():
    texts = [message("La cosecha bajó este año.")]
    result = scan_texts(texts, "es", SpyClient(), prior_flag=True)
    assert result.flag is True
    assert result.check == "done" and result.matches == []


def test_result_applies_to_the_completed_record_unchanged():
    client = SpyClient({NAME_TEXT: [ent("NAME", 0.99, NAME_TEXT, "María Torres")]})
    result = scan_texts([message(NAME_TEXT)], "es", client)
    record = CompletedRecord.model_validate(fixture_record()).model_copy(update=result.to_fields())
    assert record.pii_flag is True
    assert record.pii_check == "done"
    assert record.pii_entity_types == ["NAME"]
    assert record.model_dump(mode="json")["pii_matches"][0]["message_at"].startswith("2026-11-04")


def test_declined_record_keeps_no_narrative_content():
    data = {"record_id": "R-2", "producer_id": "258CC6A1", "status": "declined",
            "created_at": NOW, "updated_at": NOW, "version": 1,
            "consent": {"scope": "declined", "recorded_at": NOW}}
    record = DeclinedRecord.model_validate(data)
    assert getattr(record, "pii_flag", None) is None  # not even a flag lives on a declined record
    assert getattr(record, "pii_matches", None) is None
    assert getattr(record, "pii_check", None) is None


def test_pii_match_rejects_unknown_type_and_empty_text():
    ok = {"entity_type": "NAME", "text": "María Torres", "context": "Mi nombre es María Torres y", "message_at": NOW}
    assert PiiMatch.model_validate(ok).context
    with pytest.raises(ValidationError):
        PiiMatch.model_validate({**ok, "entity_type": "LOCATION"})
    with pytest.raises(ValidationError):
        PiiMatch.model_validate({**ok, "text": ""})


def test_pii_match_rejects_extra_fields():
    ok = {"entity_type": "PHONE", "text": "555-0102", "context": "llame al 555-0102 hoy", "message_at": NOW, "score": 0.9}
    with pytest.raises(ValidationError):
        PiiMatch.model_validate(ok)


def test_logs_carry_types_and_counts_not_matched_text(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="fex.pii"):
        scan_texts([message(NAME_TEXT)], "es", SpyClient({NAME_TEXT: [ent("PERSON", 0.99, NAME_TEXT, "María Torres")]}))
        scan_texts([message("La cosecha bajó.")], "es", SpyClient(fail_on=1))
    text = caplog.text
    assert "pii scan" in text
    assert "María" not in text and "Torres" not in text and "cosecha" not in text
    assert "NAME" in text


# ---------------------------------------------------------------------------------- the save path
# Issue #20 wired into #26's save: every save scans the record-bound texts and the record
# carries what the scan found. `save_record` runs the scan before it builds the record.

TABLE = "fair-exchange-records-pii"


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        t = ddb.create_table(TableName=TABLE, KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                             AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                             BillingMode="PAY_PER_REQUEST")
        yield t


def stored(table, conversation_id: str) -> dict:
    found = [i for i in table.scan()["Items"] if i["record_id"] == conversation_id]
    assert len(found) == 1
    return found[0]


NAME_ENTITIES = {NAME_TEXT: [ent("NAME", 0.99, NAME_TEXT, "María Torres")]}


def _spoken(text: str, role: str = "producer") -> SpokenEntry:
    return SpokenEntry(role=role, text=text, at=NOW)


def _correct(text: str) -> ActionEntry:
    return ActionEntry(role="action", name="correct_playback", args={"text": text}, at=NOW)


def _state(history: list, excluded=(), **overrides) -> ConversationState:
    data = {"producer_id": "P1", "conversation_id": "C1", "profile": Profile(producer_id="P1"),
            "started_at": NOW, "updated_at": NOW, "history": history}
    if excluded:
        data["excluded_history"] = list(excluded)
    data.update(overrides)
    return ConversationState(**data)


def _consent_run(table, scanner, message_text: str = "La lluvia bajó mucho y la cosecha cayó.",
                 correct: str | None = None) -> Run:
    """A completed record at consent scope 'internal', saved the way the engine saves."""
    run = Run(records=DynamoRecordStore(table), pii_scanner=scanner)
    run.small.add(intake("¿Qué ha sido difícil?"), intake("", ready=True), playback())
    run.send("start")
    run.send("message", text=message_text)
    if correct is not None:
        run.small.add(playback())  # the correction gets a fresh draft
        run.action("correct_playback", text=correct)
    run.small.add(summary())
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    run.action("set_consent", scope="internal")
    return run


def test_producer_texts_keeps_the_record_bound_texts_only():
    state = _state([_spoken("Hola, ¿cómo se encuentra?", "fex"), _spoken(NAME_TEXT),
                    _correct("Me llamo María Torres"), _spoken("   ")])
    texts = producer_texts(state)
    assert [(i, t.kind, t.text) for i, t in texts] == [(1, "message", NAME_TEXT),
                                                       (2, "correct_playback", "Me llamo María Torres")]


def test_out_of_scope_positions_are_not_collected():
    state = _state([_spoken(NAME_TEXT), _spoken("hola")], excluded=[0])
    assert [(i, t.text) for i, t in producer_texts(state)] == [(1, "hola")]


def test_scan_status_travels_with_each_text():
    state = _state([_spoken(NAME_TEXT)], consent="internal")
    assert [t.status for _, t in producer_texts(state)] == ["pending"]
    run_pii_scan(state, SpyClient({}))
    assert [(p.history_index, p.kind, p.status) for p in state.pii.per_text] == [(0, "message", "done")]


def test_declined_conversations_are_not_scanned():
    state = _state([_spoken(NAME_TEXT)], consent="declined")
    scanner = SpyClient(NAME_ENTITIES)
    run_pii_scan(state, scanner)
    assert scanner.calls == [] and state.pii is None


def test_unsupported_language_flags_at_the_save_seam():
    # A language that is neither en, es nor fr flags the record without scanning (#20, #24).
    state = _state([_spoken(NAME_TEXT)], language="pt", consent="internal")
    scanner = SpyClient(NAME_ENTITIES)
    run_pii_scan(state, scanner)
    assert scanner.calls == []
    assert (state.pii.flagged, state.pii.check) == (True, "unsupported_language")
    assert state.pii.entity_types == [] and state.pii.matches == []


def test_save_scans_the_producers_words_and_the_record_carries_them(table):
    run = _consent_run(table, SpyClient(NAME_ENTITIES), message_text=NAME_TEXT)
    record = stored(table, run.conversation_id)
    assert record["pii_flag"] is True
    assert record["pii_entity_types"] == ["NAME"]
    assert record["pii_check"] == "done"
    assert record["pii_matches"][0]["entity_type"] == "NAME" and "María Torres" in record["pii_matches"][0]["text"]


def test_newly_found_types_are_logged_once(table):
    run = _consent_run(table, SpyClient(NAME_ENTITIES), message_text=NAME_TEXT)
    run.action("set_feedback", value="yes")  # a second save rescans nothing new
    found = [(e.kind, e.refs) for e in run.state().decision_log if e.code == "pii_found"]
    assert found == [("pii", ["NAME"])]
    assert [e["refs"] for e in stored(table, run.conversation_id)["decision_log"] if e["code"] == "pii_found"] == [["NAME"]]


def test_no_pii_entry_when_nothing_is_found(table):
    run = _consent_run(table, SpyClient())
    assert not [e for e in run.state().decision_log if e.code == "pii_found"]


def test_the_correction_is_scanned_too(table):
    scanner = SpyClient(NAME_ENTITIES)
    run = _consent_run(table, scanner, correct=NAME_TEXT)
    record = stored(table, run.conversation_id)
    assert record["pii_flag"] is True and record["pii_entity_types"] == ["NAME"]
    assert NAME_TEXT in scanner.calls


def test_failed_scan_flags_the_record_without_matches(table):
    run = _consent_run(table, SpyClient(NAME_ENTITIES, fail_on=1), message_text=NAME_TEXT)
    record = stored(table, run.conversation_id)
    assert record["pii_flag"] is True and record["pii_matches"] == [] and record["pii_entity_types"] == []
    assert record["pii_check"] == "failed"


def test_done_texts_are_not_rescanned_on_the_next_save(table):
    scanner = SpyClient(NAME_ENTITIES)
    run = _consent_run(table, scanner, message_text=NAME_TEXT)
    run.action("set_feedback", value="somewhat")
    assert scanner.calls == [NAME_TEXT]
    assert stored(table, run.conversation_id)["pii_check"] == "done"


def test_an_unconfigured_scanner_adds_nothing(table):
    run = _consent_run(table, None, message_text=NAME_TEXT)
    record = stored(table, run.conversation_id)
    # Missing configuration is not a failed scan (#20): the completed record declares the pii
    # fields, so they stay at their neutral defaults instead of the scan marking anything.
    assert record["pii_flag"] is False and record["pii_entity_types"] == [] and record["pii_matches"] == []
    assert record["pii_check"] is None


def test_a_declined_record_keeps_no_pii_fields(table):
    scanner = SpyClient(NAME_ENTITIES)
    run = Run(records=DynamoRecordStore(table), pii_scanner=scanner)
    run.to_playback()
    run.small.add(summary())
    run.large.add(*RETRIEVE, run.good_answer())
    run.action("confirm_playback")
    run.action("set_consent", scope="declined")
    record = stored(table, run.conversation_id)
    assert record["status"] == "declined"
    assert not {"pii_flag", "pii_entity_types", "pii_matches", "pii_check"} & set(record)
    assert scanner.calls == []