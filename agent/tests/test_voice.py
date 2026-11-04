"""Issue #41: voice notes — local store, Transcribe streaming reduction, VoiceTurn.

Pure-logic tests only: no AWS credentials; the SDK-object fixture skips if the SDK is absent (lazy import).
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from pydantic import ValidationError

from fex.models import VoiceTurn
from fex.voice import LocalVoiceStore, ingest_voice_note, transcript_from_stream_events

NOW = datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)
SPANISH_ITEMS = [("pronunciation", "La", 0.9), ("pronunciation", "lluvia", 0.8),
                 ("pronunciation", "ha", 0.9), ("punctuation", ".", 0.9)]


def voice_turn(**overrides):
    data = {"turn_id": "t-01", "conversation_id": "C-1001", "producer_id": "258CC6A1", "created_at": NOW,
            "transcript": "La lluvia ha sido muy irregular este año.", "language_code": "es",
            "confidence": 0.87, "audio_key": "258CC6A1/C-1001/t-01.pcm"}
    data.update(overrides)
    return data


def event(result_items, language="es-US", final=True):
    """One Transcribe streaming result, shaped like the service sends it (wire PascalCase)."""
    items = [{"Type": kind, "Content": content, "Confidence": conf} for kind, content, conf in result_items]
    return {"Transcript": {"Results": [{"ResultId": "1", "IsPartial": not final,
            "Alternatives": [{"Items": items}], "LanguageCode": language}]}}


def test_final_wire_results_reduce_to_text_language_confidence():
    text, lang, confidence = transcript_from_stream_events([event(SPANISH_ITEMS)])
    assert (text, lang, confidence) == ("La lluvia ha.", "es", 0.867)  # es-US → ISO 639-1; pronunciation-only mean: (0.9+0.8+0.9)/3


def test_partial_results_are_skipped_only_finals_count():
    mixed = [event([("pronunciation", "La", 0.7)], final=False), event([("pronunciation", "Lava", 0.7)])]
    assert transcript_from_stream_events(mixed)[:2] == ("Lava", "es")
    assert transcript_from_stream_events([]) == ("", None, None)


def test_alternatives_first_wins_orphan_punctuation_dropped():
    two_alt = {"ResultId": "2", "IsPartial": False, "LanguageCode": "de-DE", "Alternatives": [
        {"Items": [{"Type": "punctuation", "Content": "!", "Confidence": None},
                   {"Type": "pronunciation", "Content": "Regen", "Confidence": 0.75}]},
        {"Items": [{"Type": "pronunciation", "Content": "WRONG", "Confidence": 0.99}]}]}
    out = transcript_from_stream_events([{"Transcript": {"Results": [two_alt]}}])
    assert out == ("Regen", "de", 0.75)  # alternatives[0]; orphan punctuation never becomes a word


def _sdk_event(sdk):
    items = [
        sdk.Item(item_type="pronunciation", content="Bonjour", start_time=0.0, end_time=0.5, confidence=0.8),
        sdk.Item(item_type="punctuation", content="!", start_time=0.5, end_time=0.6, confidence=0.0),
    ]
    alt = sdk.Alternative(transcript="Bonjour", entities=[], items=items)
    result = sdk.Result(result_id="r", is_partial=False, start_time=0.0, end_time=1.0,
                        language_code="fr-FR", alternatives=[alt])
    return sdk.TranscriptEvent(transcript=sdk.Transcript(results=[result]))


def test_sdk_object_events_reduce_like_the_live_stream():
    sdk = pytest.importorskip("amazon_transcribe.model")
    ev = _sdk_event(sdk)
    assert transcript_from_stream_events([ev]) == ("Bonjour!", "fr", 0.8)  # attr access, punctuation conf excluded


def test_voice_turn_rejects_bad_language_unknown_fields_and_bad_confidence():
    for bad in (voice_turn(language_code="spa"),  # ISO 639-1 only
                {**voice_turn(), "transcript_override": "nope"},  # extra="forbid" backstop
                voice_turn(confidence=1.2)):  # must stay in [0, 1]
        with pytest.raises(ValidationError):
            VoiceTurn.model_validate(bad)


def test_store_rejects_bad_extensions_bad_segments_and_escaping_keys(tmp_path):
    store = LocalVoiceStore(tmp_path)
    for bad in ("../evil", "a/b", "", "..", "a\\b"):
        with pytest.raises(ValueError):
            store.save_audio(bad, "C-1001", "t-01", b"x")
    with pytest.raises(ValueError):
        store.save_audio("258CC6A1", "C-1001", "t-01", b"x", ext="up/1")
    with pytest.raises(ValueError):
        store.audio_path("../../etc/passwd")
    with pytest.raises(FileNotFoundError):
        store.audio_path("258CC6A1/C-1001/missing.pcm")


def test_ingest_writes_audio_and_sidecar_and_returns_the_turn(tmp_path):
    store = LocalVoiceStore(tmp_path)
    turn = ingest_voice_note(store, producer_id="258CC6A1", conversation_id="C-1001", turn_id="t-01",
                             audio=b"audio-bytes", events=[event(SPANISH_ITEMS)])
    assert (turn.transcript, turn.language_code, turn.pii_flag) == ("La lluvia ha.", "es", False)
    assert turn.audio_key == "258CC6A1/C-1001/t-01.pcm"
    assert store.audio_path(turn.audio_key).read_bytes() == b"audio-bytes"
    sidecar = json.loads((tmp_path / "258CC6A1/C-1001/t-01.transcript.json").read_text())
    assert sidecar["turn_id"] == "t-01"
    trio = ingest_voice_note(LocalVoiceStore(tmp_path), producer_id="258CC6A1", conversation_id="C-1001",
                             turn_id="t-03", audio=b"raw", transcript_result=("Hola.", "es-US", 0.9))
    assert (trio.transcript, trio.language_code, trio.confidence) == ("Hola.", "es", 0.9)  # pre-reduced trio path


def test_ingest_rejects_empty_transcript_but_keeps_audio_resting(tmp_path):
    store = LocalVoiceStore(tmp_path)
    with pytest.raises(ValueError, match="empty transcript"):
        ingest_voice_note(store, producer_id="258CC6A1", conversation_id="C-1001", turn_id="t-01",
                          audio=b"silence", events=[event(SPANISH_ITEMS, final=False)])
    assert store.audio_path("258CC6A1/C-1001/t-01.pcm").read_bytes() == b"silence"


def test_ingest_refuses_missing_language_code_instead_of_guessing(tmp_path):
    store = LocalVoiceStore(tmp_path)
    no_lang = [{"Transcript": {"Results": [{"IsPartial": False, "Alternatives": [
        {"Items": [{"Type": "pronunciation", "Content": "hello", "Confidence": 0.9}]}]}]}}]
    with pytest.raises(ValueError, match="language"):
        ingest_voice_note(store, producer_id="258CC6A1", conversation_id="C-1001", turn_id="t-02",
                          audio=b"raw", events=no_lang)
    assert store.audio_path("258CC6A1/C-1001/t-02.pcm")  # audio rests for retry


@pytest.mark.parametrize("kind", ["audio", "transcript"])
def test_overlapping_store_writes_keep_one_complete_payload(tmp_path, monkeypatch, kind):
    store = LocalVoiceStore(tmp_path)
    key = "258CC6A1/C-1001/t-01.pcm"
    turns = [VoiceTurn(**voice_turn(transcript=text)) for text in ("Hola.", "Una nota más larga.")]
    payloads = [b"first", b"a longer second recording"] if kind == "audio" else [
        turn.model_dump_json().encode("utf-8") for turn in turns
    ]
    destination = tmp_path / (key if kind == "audio" else key.replace(".pcm", ".transcript.json"))
    ready_to_replace = Barrier(2)
    replace = os.replace

    def overlapping_replace(source, target, *args, **kwargs):
        # Both writers finish their temporary files before either publishes one.
        ready_to_replace.wait(timeout=5)
        return replace(source, target, *args, **kwargs)

    monkeypatch.setattr(os, "replace", overlapping_replace)

    def save(index):
        if kind == "audio":
            return store.save_audio("258CC6A1", "C-1001", "t-01", payloads[index])
        return store.save_transcript(key, turns[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(save, range(2)))  # Both calls must complete without losing a temporary file.

    assert destination.read_bytes() in payloads
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == [destination]


@pytest.mark.parametrize("kind", ["audio", "transcript"])
def test_failed_store_replacement_preserves_existing_file_and_removes_temp(tmp_path, monkeypatch, kind):
    store = LocalVoiceStore(tmp_path)
    key = "258CC6A1/C-1001/t-01.pcm"

    def save(text):
        if kind == "audio":
            store.save_audio("258CC6A1", "C-1001", "t-01", text.encode("utf-8"))
        else:
            store.save_transcript(key, VoiceTurn(**voice_turn(transcript=text)))

    save("Original note.")
    destination = tmp_path / (key if kind == "audio" else key.replace(".pcm", ".transcript.json"))
    original = destination.read_bytes()

    def fail_replace(*args, **kwargs):
        raise OSError("replacement failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        save("Replacement note.")

    assert destination.read_bytes() == original
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == [destination]
