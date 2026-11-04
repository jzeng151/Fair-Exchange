"""Code review on #45: the exported JSON Schema must reject what the Python models reject.
Otherwise anything validating with the JSON Schema (e.g. the TypeScript API) would accept records
the source of truth forbids, such as storing content after the producer declined."""
import json

import jsonschema
import pytest
from pydantic import ValidationError

from fex.models import parse_record
from fex.schema_export import export_json_schema

NOW = "2026-11-04T15:30:00Z"
CLAIM = {"text": "Rainfall was low.", "citation": {"source": "CHIRPS rainfall", "standard_clause": "APS 3.6.1"}}


def completed(**overrides):
    data = {
        "record_id": "R-1", "producer_id": "P-1", "status": "completed", "created_at": NOW,
        "updated_at": NOW, "version": 1, "evidence": "full",
        "consent": {"scope": "internal", "recorded_at": NOW},
        "language": "es", "entity_type": "cooperative",
        "summary_original": "La lluvia ha sido irregular.", "summary_english": "Rainfall has been irregular.",
        "tags": ["climate and weather"], "insights": [CLAIM], "peer_examples": [],
    }
    data.update(overrides)
    return data


def declined(**overrides):
    data = {"record_id": "R-2", "producer_id": "P-1", "status": "declined", "created_at": NOW,
            "updated_at": NOW, "version": 1,
            "consent": {"scope": "declined", "recorded_at": NOW}}
    data.update(overrides)
    return data


SCHEMA = json.loads(export_json_schema())


def schema_accepts(payload) -> bool:
    try:
        jsonschema.validate(payload, SCHEMA)
        return True
    except jsonschema.ValidationError:
        return False


def python_accepts(payload) -> bool:
    try:
        parse_record(payload)
        return True
    except ValidationError:
        return False


REJECTED = {
    "completed record stored after a decline": completed(consent={"scope": "declined", "recorded_at": NOW}),
    "declined record with a storage consent": declined(consent={"scope": "internal", "recorded_at": NOW}),
    "non-English record without English summary": completed(summary_english=None),
    "non-English record with empty English summary": completed(summary_english=""),
    "declined record with narrative content": declined(summary_original="No quiero que guarden esto."),
    "claim without a citation": completed(insights=[{"text": "Rainfall was low."}]),
    "tag outside the 11-tag set": completed(tags=["drought"]),
}
ACCEPTED = {
    "completed Spanish record": completed(),
    "completed English record without a second summary": completed(language="en", summary_english=None),
    "completed record with outward sharing": completed(consent={"scope": "internal_and_outward", "recorded_at": NOW}),
    "declined record": declined(),
}


@pytest.mark.parametrize("payload", REJECTED.values(), ids=REJECTED.keys())
def test_json_schema_rejects_what_python_rejects(payload):
    assert not python_accepts(payload)
    assert not schema_accepts(payload)


@pytest.mark.parametrize("payload", ACCEPTED.values(), ids=ACCEPTED.keys())
def test_json_schema_accepts_what_python_accepts(payload):
    assert python_accepts(payload)
    assert schema_accepts(payload)


@pytest.mark.parametrize("bad", [
    pytest.param(lambda: declined(evidence="full"), id="declined-with-evidence"),
    pytest.param(lambda: declined(earlier_answers=[]), id="declined-with-earlier-answers"),
    pytest.param(lambda: completed(version=0), id="version-0"),
    pytest.param(lambda: completed(evidence="partial"), id="unknown-evidence"),
    pytest.param(lambda: {k: v for k, v in completed().items() if k != "version"}, id="missing-version"),
])
def test_json_schema_rejects_what_the_models_reject_for_write_back_fields(bad):
    payload = bad()
    with pytest.raises(ValidationError):
        parse_record(payload)
    assert not schema_accepts(payload)
