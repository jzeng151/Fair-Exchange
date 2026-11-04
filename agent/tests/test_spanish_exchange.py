"""Issue #22: Spanish exchange and bilingual record. Spec: docs/specs/22-spanish-exchange.md.

Seam 1 (agent entrypoint) with scripted Spanish model output.
"""
import boto3
import pytest
from moto import mock_aws
from pydantic import ValidationError
from tests.conversation_harness import RETRIEVE, Run, intake, of, playback, summary

from fex.conversation.state import Profile
from typing import get_args

from fex.models import ChallengeTag, CompletedRecord

CHALLENGE_TAG_VALUES = get_args(ChallengeTag)
from fex.records import DynamoRecordStore


def langs(events) -> set[str]:
    return {e.language for e in of(events, "step") + of(events, "actions")}


# ---------------------------------------------------------------- opening language

def test_opening_is_in_english_when_the_profile_has_no_language():
    r = Run()
    r.small.add(intake("What has been difficult this year?", language="es"))  # the model guesses Spanish
    events = r.send("start")
    assert r.state().language == "en"  # the opening rule wins over a guess: nobody has written yet
    assert langs(events) == {"en"}


def test_opening_uses_the_language_in_the_producers_profile():
    def profiles(pid):
        return Profile(producer_id=pid, country="Colombia", region="Cauca", crop="Coffee",
                       entity_type="cooperative", language="es")
    r = Run(profiles=profiles)
    r.small.add(intake("¿Qué ha sido lo más difícil este año?", language="en"))  # the model's guess must not win
    events = r.send("start")
    assert r.state().language == "es" and langs(events) == {"es"}
    assert "es" in r.small.prompts[-1]  # the model is told which language to open in


def test_fex_switches_once_intake_identifies_the_producers_language():
    r = Run()
    r.small.add(intake("What has been difficult?", language="en"))
    r.send("start")
    r.small.add(intake("¿Desde cuándo pasa?", language="es"))
    events = r.send("message", text="La lluvia bajó mucho.")
    assert r.state().language == "es" and langs(events) == {"es"}


# ---------------------------------------------------------------- spec testing decisions

def test_language_is_stored_as_es():
    r = Run()
    r.to_playback()
    assert r.state().language == "es"


def test_step_actions_and_resume_carry_es_once_identified():
    r = Run()
    events = r.to_playback()
    assert langs(events) == {"es"}
    assert r.send("resume").language == "es"


def test_fixed_answer_text_is_in_spanish():
    r = Run()
    text = "".join(e.text for e in of(r.to_consent(), "text"))
    assert "Esto es lo que encontré" in text and "Usted y su comité conocen mejor su situación" in text


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        yield ddb.create_table(TableName="records", KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                               AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                               BillingMode="PAY_PER_REQUEST")


def test_the_spanish_record_has_both_summaries_and_english_tags(table):
    r = Run(records=DynamoRecordStore(table))
    r.to_consent()
    r.action("set_consent", scope="internal")
    item = table.scan()["Items"][0]
    assert item["language"] == "es"
    assert item["summary_original"] == "La lluvia bajó." and item["summary_english"] == "Rain fell."
    assert item["tags"] and set(item["tags"]) <= set(CHALLENGE_TAG_VALUES)  # English values of the 11-tag set


def test_a_spanish_record_without_summary_english_is_rejected():
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate({
            "record_id": "R", "producer_id": "P", "status": "completed", "created_at": "2026-11-04T12:00:00Z",
            "updated_at": "2026-11-04T12:00:00Z", "version": 1, "evidence": "full",
            "consent": {"scope": "internal", "recorded_at": "2026-11-04T12:00:00Z"},
            "language": "es", "entity_type": "cooperative", "summary_original": "La lluvia bajó.",
            "tags": ["water"]})


def test_spanish_tags_are_rejected():
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate({
            "record_id": "R", "producer_id": "P", "status": "completed", "created_at": "2026-11-04T12:00:00Z",
            "updated_at": "2026-11-04T12:00:00Z", "version": 1, "evidence": "full",
            "consent": {"scope": "internal", "recorded_at": "2026-11-04T12:00:00Z"},
            "language": "es", "entity_type": "cooperative", "summary_original": "La lluvia bajó.",
            "summary_english": "Rain fell.", "tags": ["agua"]})
