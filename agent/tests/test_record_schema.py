"""Issue #6: the conversation record schema (the record IS the product)."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from fex.models import CompletedRecord, DeclinedRecord, parse_record

NOW = datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)


def completed(**overrides):
    """A hand-written, valid completed record (Spanish conversation)."""
    data = {
        "record_id": "R-0001",
        "producer_id": "258CC6A1",
        "status": "completed",
        "created_at": NOW,
        "consent": {"scope": "internal", "recorded_at": NOW},
        "language": "es",
        "entity_type": "cooperative",
        "summary_original": "La lluvia ha sido muy irregular y la cosecha bajó.",
        "summary_english": "Rainfall has been very irregular and the harvest dropped.",
        "tags": ["climate and weather", "water"],
        "insights": [{
            "text": "Rainfall in Cauca was about 22% below the 10-year average.",
            "citation": {"source": "CHIRPS rainfall", "standard_clause": "APS 3.2.1", "strength": "exact"},
        }],
        "peer_examples": [{
            "text": "A cooperative in Huila funded rainwater catchment with Premium.",
            "citation": {"source": "FTUSA Premium project record", "standard_clause": "APS 3.2.1", "strength": "nearest"},
        }],
    }
    data.update(overrides)
    return data


def test_completed_record_defaults_source_and_review_status():
    record = CompletedRecord.model_validate(completed())
    assert record.source == "agent conversation"
    assert record.review_status == "pending"


def test_claim_without_citation_is_rejected():
    no_citation = [{"text": "Rainfall was about 22% below average."}]
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate(completed(insights=no_citation))


def test_citation_with_empty_standard_clause_is_rejected():
    empty_clause = [{"text": "Rainfall was low.", "citation": {"source": "CHIRPS rainfall", "standard_clause": ""}}]
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate(completed(peer_examples=empty_clause))


def test_tag_outside_the_eleven_challenge_tags_is_rejected():
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate(completed(tags=["drought"]))  # "climate and weather" is the real tag


def test_source_cannot_claim_to_be_compliance_data():
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate(completed(source="compliance audit"))


def test_consent_must_be_a_scope_not_a_yes_no():
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate(completed(consent={"scope": "yes", "recorded_at": NOW}))


def test_completed_record_accepts_outward_sharing_scope():
    record = CompletedRecord.model_validate(completed(consent={"scope": "internal_and_outward", "recorded_at": NOW}))
    assert record.consent.scope == "internal_and_outward"


def test_completed_record_cannot_carry_declined_consent():
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate(completed(consent={"scope": "declined", "recorded_at": NOW}))


def declined(**overrides):
    """A hand-written, valid declined record: identifiers, status and time only."""
    data = {
        "record_id": "R-0002",
        "producer_id": "258CC6A1",
        "status": "declined",
        "created_at": NOW,
        "consent": {"scope": "declined", "recorded_at": NOW},
    }
    data.update(overrides)
    return data


def test_declined_record_holds_only_identifiers_and_time():
    record = DeclinedRecord.model_validate(declined())
    assert record.producer_id == "258CC6A1"
    assert record.source == "agent conversation"


@pytest.mark.parametrize("narrative_field, value", [
    ("summary_original", "No quiero que guarden esto."),
    ("summary_english", "I don't want this saved."),
    ("tags", ["water"]),
    ("insights", []),
    ("feedback", "no"),
])
def test_declined_record_rejects_any_narrative_content(narrative_field, value):
    with pytest.raises(ValidationError):
        DeclinedRecord.model_validate(declined(**{narrative_field: value}))


def test_declined_record_must_carry_declined_consent():
    with pytest.raises(ValidationError):
        DeclinedRecord.model_validate(declined(consent={"scope": "internal", "recorded_at": NOW}))


def test_parse_record_picks_the_type_from_status():
    assert type(parse_record(completed())) is CompletedRecord
    assert type(parse_record(declined())) is DeclinedRecord


def test_completed_record_requires_producer_id():
    data = completed()
    del data["producer_id"]
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate(data)


def test_non_english_record_requires_english_summary():
    with pytest.raises(ValidationError):
        CompletedRecord.model_validate(completed(language="es", summary_english=None))


def test_english_record_does_not_need_a_second_summary():
    record = CompletedRecord.model_validate(completed(
        language="en", summary_original="Rainfall has been irregular.", summary_english=None))
    assert record.summary_english is None
