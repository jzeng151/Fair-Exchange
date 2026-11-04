"""Seeded conversation records for the dashboard (#37): the pure generator.

Validation against the record models (`fex.models.parse_record`) lives in agent/tests, because the
record models are in the agent package and the data package must not import it.
"""
import json
from collections import Counter

from fx_data.peers import ProducerProfiles
from fx_data.seeded_records import CHALLENGE_TAGS, generate_seeded_records

# Fields a declined record may carry: identifiers, status, times, consent, consent history and AI usage
NON_NARRATIVE = {"record_id", "producer_id", "status", "created_at", "updated_at", "version", "closed_at",
                 "source", "consent", "consent_history", "ai_usage"}

RECORDS = generate_seeded_records()
COMPLETED = [r for r in RECORDS if r["status"] == "completed"]
DECLINED = [r for r in RECORDS if r["status"] == "declined"]


def test_the_same_seed_gives_the_same_output():
    assert generate_seeded_records() == generate_seeded_records()
    assert json.dumps(generate_seeded_records(seed=7)) == json.dumps(generate_seeded_records(seed=7))


def test_a_different_seed_gives_a_different_output():
    assert generate_seeded_records(seed=1) != generate_seeded_records(seed=2)


def test_about_200_records_with_unique_synthetic_ids():
    assert 180 <= len(RECORDS) <= 220
    ids = [r["record_id"] for r in RECORDS]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("SEED-") for i in ids)


def test_records_are_plain_json():
    assert json.loads(json.dumps(RECORDS)) == RECORDS


def test_every_tag_language_and_granted_scope_has_at_least_5_completed_records():
    tags = Counter(t for r in COMPLETED for t in r["tags"])
    assert set(tags) == CHALLENGE_TAGS
    assert min(tags.values()) >= 5, tags
    languages = Counter(r["language"] for r in COMPLETED)
    assert set(languages) == {"en", "es"} and min(languages.values()) >= 5, languages
    scopes = Counter(r["consent"]["scope"] for r in COMPLETED)
    assert set(scopes) == {"internal", "internal_and_outward"} and min(scopes.values()) >= 5, scopes


def test_at_least_5_declined_records():
    assert len(DECLINED) >= 5
    assert all(r["consent"]["scope"] == "declined" for r in DECLINED)


def test_declined_records_have_no_narrative():
    for r in DECLINED:
        assert set(r) <= NON_NARRATIVE, sorted(set(r) - NON_NARRATIVE)


def test_covers_feedback_evidence_review_status_and_entity_types():
    assert {r.get("feedback") for r in COMPLETED} == {"yes", "somewhat", "no", None}
    assert {r["evidence"] for r in COMPLETED} == {"full", "limited"}
    assert {r["review_status"] for r in COMPLETED} == {"pending", "reviewed"}
    assert len({r["entity_type"] for r in COMPLETED}) >= 4


def test_limited_evidence_means_no_insights_or_no_peer_examples():
    for r in COMPLETED:
        limited = not r["insights"] or not r["peer_examples"]
        assert (r["evidence"] == "limited") == limited, r["record_id"]


def test_producers_come_from_the_producer_table():
    profiles = ProducerProfiles.load()
    for r in RECORDS:
        assert profiles.get(r["producer_id"]) is not None, r["producer_id"]
    for r in COMPLETED:
        expected = profiles.get(r["producer_id"]).entity_type or "unknown"
        assert r["entity_type"] == expected


def test_consent_history_ends_with_the_final_choice():
    for r in RECORDS:
        history = [c["scope"] for c in r["consent_history"]]
        assert history and history[-1] == r["consent"]["scope"]
        assert r["consent_history"][-1]["recorded_at"] == r["consent"]["recorded_at"]
        assert all(a != b for a, b in zip(history, history[1:])), history  # distinct choices


def test_every_record_has_plausible_ai_usage():
    for r in RECORDS:
        assert r["ai_usage"], r["record_id"]
        for u in r["ai_usage"]:
            assert u["model_id"].startswith("us.anthropic.claude-")
            assert 50 <= u["input_tokens"] <= 50_000 and 10 <= u["output_tokens"] <= 10_000
    assert len({u["model_id"] for r in RECORDS for u in r["ai_usage"]}) == 2


def test_text_is_marked_synthetic():
    for r in COMPLETED:
        assert r["summary_original"].startswith(("[Synthetic]", "[Sintético]"))
        if r["language"] != "en":
            assert r["summary_english"].startswith("[Synthetic]")
