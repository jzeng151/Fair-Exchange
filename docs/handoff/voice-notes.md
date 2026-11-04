# Mini spec — voice notes → Transcribe → ingestion (#41)
How a producer voice note becomes a `VoiceTurn`. Status: implemented on branch
`feature/voice-notes-transcribe`; endpoint handler + storage location land later.

## Flow
1. **Capture** (`web/voice-capture.js`): mic → AudioWorklet → 16 kHz mono **PCM16**, 60 s cap, chunked base64 in 3-byte-multiple blocks (naive `btoa` spreads die on real audio; mid-stream `=` padding would corrupt decode — blocks multiple of 3 keep padding at the true end only).
2. **POST** `{conversation_id, media_encoding: "pcm", sample_rate: 16000, pcm_b64}` to the chat API's voice endpoint.
3. **Endpoint** (future PR): derives `producer_id` from the **login session** — never the client, never a model — allocates `turn_id`, calls `ingest_voice_note(store, producer_id=..., ...)` (`fex.voice`).
4. **Transcribe** (us-west-2 only, per kickoff): `run_stream_transcription` streams ≤32 KB audio events through `start_stream_transcription` (`media_sample_rate_hz`, `identify_language=True`, `language_options=["es-US","en-US","fr-FR","de-DE"]` — the SDK takes **full BCP-47 locales**, Spanish first ~77% LatAm).
5. **Ingest**: reducer accepts SDK event objects (`.transcript.results`, items carry `item_type`) or raw wire dicts → `(transcript, language_code, confidence)`; `es-US → es` normalized (ISO 639-1); `VoiceTurn` built (`agent/src/fex/models.py`); audio + `.transcript.json` sidecar persisted.

## Contracts
- **Client → endpoint:** only the four POST fields. `VoiceTurn` is `extra="forbid"` as backstop.
- **Storage (`fex.voice.VoiceStore`):** `save_audio(...) -> key`, `audio_path(key) -> path`, `save_transcript(key, turn) -> None`. Layout `data/voice-notes/<producer>/<conversation>/<turn>.<ext>` (default `.pcm`) + sidecar; every segment validated (`_segment`) — traversal/empty/separators refused. Each write uses a unique temporary file in the destination directory, then atomically replaces its target. Overlapping writes to one file use last-replacement-wins semantics; audio and sidecar writes are separate operations. Failed writes remove their temporary files.
- **`VoiceTurn`:** turn_id, conversation_id, producer_id, created_at, transcript, language_code (ISO 639-1), confidence ∈ [0, 1], audio_key (opaque), pii_flag (starts `False`).

## Decisions left for Jason (single-point swaps, no rework)
- **Storage → S3:** an `S3VoiceStore` with the same three methods; the `audio_key` shape (`258CC6A1/C-1001/t-01.pcm`) maps straight to object keys. Local is the only backend today; nothing else in the pipeline changes.
- **PII pass (#20):** raises `pii_flag`; redaction stays OFF until then (flag, never redact).
- **Endpoint:** ~15 lines around `ingest_voice_note`, rides the chat API once #25/#13 settle the turn surface.

## Ops notes
- Capture releases microphone tracks and audio nodes on stop or initialization failure, closes the audio context, and revokes the worklet blob URL after initialization. Initialization failures never upload a note.
- Empty transcripts refuse to ingest — and a missing `language_code` **fails loudly** (no silent "en" guess); audio still rests either way: retry-safe (deterministic turn_id per session).
- Credential-free tests; the reducer covers SDK objects, wire dicts, and partials. `amazon-transcribe` imports lazily inside `run_stream_transcription` — declared for the live path; SDK-object test fixture skips if absent.
- Confidence averages **pronunciation items only** — punctuation padding (often 0.0) would skew it; `alternatives[0]` is the service-final hypothesis.
- Long-term: real-time partial-transcript echo in the UI (streaming supports partials; the reducer deliberately waits for finals).
