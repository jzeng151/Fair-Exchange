"""Issue #41 (voice notes): capture → Transcribe streaming (us-west-2) → VoiceTurn; local-first `VoiceStore` (S3 swaps in later); lazy SDK import keeps tests credential-free."""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Protocol

from fex.models import VoiceTurn

_DEFAULT_AUDIO_EXT = "pcm"
_MAX_CHUNK = 32768  # Amazon Transcribe audio-event cap (32 KB)
_TRANSCRIPT_SUFFIX = ".transcript.json"


def _segment(value: str, name: str) -> str:
    """Validate one path segment; refuse traversal, separators, and empties."""
    if not value or value in (".", "..") or "/" in value or "\\" in value:
        raise ValueError(f"{name} must be a single path segment")
    return value


def _atomic_write(path: Path, data: bytes) -> None:
    """Publish one complete file; overlapping writers own separate temporary files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".part", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(data)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class VoiceStore(Protocol):
    """Where voice notes rest. Local dir today; the S3 swap lands here later."""

    def save_audio(self, producer_id: str, conversation_id: str, turn_id: str, audio: bytes, ext: str) -> str: ...
    def audio_path(self, audio_key: str) -> Path: ...
    def save_transcript(self, audio_key: str, turn: VoiceTurn) -> None: ...


class LocalVoiceStore:
    """Local-first backend: data/voice-notes/<producer>/<conversation>/<turn>.*."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _resolve(self, key: str) -> Path:
        path = self.root.joinpath(*(_segment(s, f"audio key {key!r}") for s in key.split("/")))
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError(f"audio key escapes the voice store: {key!r}")
        return path

    def save_audio(self, producer_id: str, conversation_id: str, turn_id: str, audio: bytes,
                   ext: str = _DEFAULT_AUDIO_EXT) -> str:
        if not ext.isalnum() or len(ext) > 8:
            raise ValueError(f"audio extension must be short and alphanumeric: {ext!r}")
        key = "/".join((_segment(producer_id, "producer_id"), _segment(conversation_id, "conversation_id"),
                        _segment(turn_id, "turn_id") + "." + ext))
        _atomic_write(self._resolve(key), audio)
        return key

    def audio_path(self, audio_key: str) -> Path:
        path = self._resolve(audio_key)
        if not path.is_file():
            raise FileNotFoundError(audio_key)
        return path

    def save_transcript(self, audio_key: str, turn: VoiceTurn) -> None:
        sidecar = self._resolve(audio_key.rsplit(".", 1)[0] + _TRANSCRIPT_SUFFIX)
        _atomic_write(sidecar, turn.model_dump_json().encode("utf-8"))


def _f(obj, name):
    """Read `name` off SDK objects or dicts (snake_case keys, wire PascalCase fallback)."""
    if isinstance(obj, dict):
        return obj.get(name, obj.get(name.title().replace("_", "")))
    return getattr(obj, name, None)


def transcript_from_stream_events(events: Iterable[object]) -> tuple[str, str | None, float | None]:
    """Streaming events (SDK objects, wire dicts, snake dicts) → (final text, ISO 639-1 language, mean pronunciation confidence); partials and later alternatives set aside."""
    chunks, confidences, language = [], [], None
    for event in events:
        transcript = _f(event, "transcript") or _f(event, "transcript_event")
        for result in _f(transcript, "results") or []:
            if _f(result, "is_partial"):
                continue
            if code := _f(result, "language_code"):
                language = code.split("-")[0].lower()  # es-US → es: the record language is ISO 639-1 (#22)
            words: list[str] = []
            alt = (_f(result, "alternatives") or [None])[0]
            for item in _f(alt, "items") or []:
                kind, content = _f(item, "item_type") or _f(item, "type"), _f(item, "content")
                if kind == "punctuation":
                    if words:
                        words[-1] += content or ""
                    continue  # orphan punctuation (no preceding word) never becomes a word
                words.append(content or "")
                if (conf := _f(item, "confidence")) is not None:
                    confidences.append(float(conf))  # pronunciation only; None tolerated
            if words:
                chunks.append(" ".join(words))
    text = " ".join(chunks).strip()
    return text, language, (round(sum(confidences) / len(confidences), 3) if confidences else None)


def run_stream_transcription(audio_chunks: Iterable[bytes], region: str = "us-west-2", media_encoding: str = "pcm",
                             sample_rate: int = 16000, language_options: list[str] | None = None) -> tuple[str, str | None, float | None]:
    """Live Transcribe streaming (us-west-2)."""
    import asyncio
    from amazon_transcribe.client import TranscribeStreamingClient

    async def _run() -> tuple[str, str | None, float | None]:
        client = TranscribeStreamingClient(region=region)
        stream = await client.start_stream_transcription(
            language_code=None,
            media_sample_rate_hz=sample_rate,
            media_encoding=media_encoding,
            identify_language=True,
            language_options=list(language_options or ["es-US", "en-US", "fr-FR", "de-DE"]),
        )

        async def _feed() -> None:
            try:
                for chunk in audio_chunks:  # re-slice: callers may hand over-big buffers
                    for i in range(0, len(chunk), _MAX_CHUNK):
                        await stream.input_stream.send_audio_event(audio_chunk=chunk[i:i + _MAX_CHUNK])
            finally:
                await stream.input_stream.end_stream()  # never leave the stream open on feed errors

        feed = asyncio.ensure_future(_feed())
        payloads = [event async for event in stream.output_stream]  # SDK TranscriptEvent objects
        await feed
        return transcript_from_stream_events(payloads)

    return asyncio.run(_run())


def ingest_voice_note(store: VoiceStore, *, producer_id: str, conversation_id: str, turn_id: str | None,
                      audio: bytes, events: Iterable[object] | None = None,
                      transcript_result: tuple[str, str | None, float | None] | None = None,
                      created_at: datetime | None = None, media_ext: str = _DEFAULT_AUDIO_EXT) -> VoiceTurn:
    """Persist audio, reduce events (or take run_stream_transcription's trio), build VoiceTurn; segments come from the session, never a model."""
    turn_id = turn_id or f"turn-{uuid.uuid4().hex[:12]}"
    audio_key = store.save_audio(producer_id, conversation_id, turn_id, audio, ext=media_ext)
    transcript, language_code, confidence = transcript_result or transcript_from_stream_events(events or [])
    if not transcript: raise ValueError(f"transcription produced an empty transcript for {audio_key!r}")  # audio rests
    language_code = (language_code or "").split("-")[0].lower()
    if len(language_code) != 2 or not language_code.isalpha(): raise ValueError(f"missing language_code for {audio_key!r}")
    turn = VoiceTurn(turn_id=turn_id, conversation_id=conversation_id, producer_id=producer_id,
                     created_at=created_at or datetime.now(timezone.utc), transcript=transcript,
                     language_code=language_code, confidence=confidence, audio_key=audio_key,
                     pii_flag=False)  # flag, never redact: the flagging pass (#20) raises this later
    store.save_transcript(audio_key, turn)
    return turn
