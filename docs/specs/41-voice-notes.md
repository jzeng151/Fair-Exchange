# Spec: Voice notes via Amazon Transcribe (#41)

Status: approved for build, 2026-11-04. Nice-to-have: start only after every must-have is done.

## Problem Statement

Some producers find speaking easier than typing, especially on a phone or in their second language. The MVP is text-only. Voice input must not weaken the rules that text follows:
- the producer sees and controls what is sent;
- scope and ownership checks apply;
- PII is flagged, not lost;
- audio doesn't pile up as a new store of producer data.

## Solution

The producer records a short voice note in the chat. It is uploaded to a private bucket and transcribed with Amazon Transcribe. The transcript is placed in the message box for the producer to review and edit. Nothing reaches FEX until the producer presses send, and the sent text is then an ordinary message. The audio and the raw transcript are deleted once transcription finishes.

## User Stories

1. As a producer, I want to record a voice note instead of typing, so that I can describe my challenge more easily.
2. As a producer, I want to see and edit the transcript before it is sent, so that FEX only receives what I meant to say.
3. As a producer, I want voice notes in English, Spanish (and French with #24), so that I can speak my language.
4. As a producer, I want a clear recording indicator and a way to cancel, so that I know when I'm being recorded.
5. As a producer using a keyboard or screen reader, I want the record control fully accessible, and typing always available, so that voice is an option, never a requirement.
6. As an FTUSA engineer, I want audio deleted after transcription, so that voice doesn't create a new store of producer recordings.
7. As an FTUSA engineer, I want voice routes to follow the same ownership and scope checks as chat, so that nobody can transcribe into someone else's conversation.

## Implementation Decisions

### Routes

These are on the same REST API, TypeScript on Node.js 24, `producer` role, with the conversation ownership check from [#25](25-chat-endpoint.md). The conversation must be open.

| Method and path | Purpose |
|---|---|
| `POST /conversations/{id}/voice` | Creates a `voice_id` and returns a pre-signed POST form: URL plus fields. It is valid for 5 minutes. Its policy fixes the key under the conversation's prefix, limits `Content-Type` to `audio/webm` or `audio/mp4` (Safari records MP4), and sets `content-length-range` to at most 5 MB. |
| `POST /conversations/{id}/voice/{voice_id}/transcribe` | Starts a Transcribe batch job and returns 202. |
| `GET /conversations/{id}/voice/{voice_id}` | Returns `status` (`pending`, `done`, `delivered`, `failed`, `cancelled`) and, the first time it is `done`, `transcript` (see transcript lifetime below). After `expires_at`, it returns 404. |
| `DELETE /conversations/{id}/voice/{voice_id}` | Cancels. It marks the item `cancelled` and deletes the audio. Transcribe batch jobs can't be stopped, so a job already running finishes, and its result is discarded by the completion worker. |

### Transcription

- **Language.** The conversation's language if identified. Otherwise Transcribe's language identification is limited to `en-US`, `es-US` and `fr-FR` (only `en` and `es` until #24 is built).
- **Job.** A batch job, with output written to the voice bucket.
- **Completion worker.** An EventBridge rule on Transcribe job state changes (completed or failed) triggers a worker Lambda. It doesn't depend on the browser:
  - on completion it deletes the audio and job output. It stores the transcript on the voice item only if the item isn't `cancelled`;
  - on failure it marks the item `failed`, unless cancelled, and deletes the audio.
  - Cleanup is idempotent, so a repeat event is harmless.
- **Voice items.** A small voice table (key `voice_id`) holds `conversation_id`, `status`, `expires_at` (one hour after creation) and, until it is delivered, the transcript.
- **Transcript lifetime.** The first `GET` that returns the transcript also removes it from the item and sets `status` to `delivered`. A later `GET` returns `delivered` with no transcript. Any `GET` after `expires_at` returns 404. DynamoDB TTL on `expires_at` removes the item itself later; TTL deletion can take days, so it is not relied on to remove transcripts.
- **Limits.** Recordings are at most 2 minutes. Failed jobs return `failed`, and the producer can type instead.

### Client

- **Recording.** Records with the browser's media recorder: `audio/webm` (Opus) where supported, otherwise `audio/mp4`.
- **Indicator.** Shows a visible and announced recording state, with stop and cancel controls.
- **Polling.** Polls the status route every 2 seconds, for up to 90 seconds.
- **Review before sending.** Puts the transcript in the message box for editing and sends it as an ordinary `message` ([#25](25-chat-endpoint.md)) only when the producer presses send.

### Storage and data rules

- **Voice bucket:**
  - KMS-encrypted, public access blocked;
  - a lifecycle rule deletes any object older than 1 day, as a backstop to the explicit deletes.
- **Deletion (decided 2026-11-04 while writing).** The completion worker deletes the audio and raw Transcribe output as soon as the job finishes or fails. Cancelling deletes the audio at once. A transcript is removed as soon as it has been delivered once, and is never returned after one hour.
- **CORS.** The voice bucket allows `POST` from the web app's CloudFront origin only.
- **Roles:**
  - **Voice route handler:** read on the conversations table (ownership check), read and write on the voice table, write and delete on the voice bucket prefix (cancellation), `transcribe:StartTranscriptionJob`, and the KMS key.
  - **Completion worker:** `transcribe:GetTranscriptionJob`, read and delete on the voice bucket, write on the voice table, and the KMS key.
- **PII and scope.**
  - The sent transcript is producer-typed text, so it gets the PII check ([#20](20-pii-flagging.md)) and the out-of-scope check ([#21](21-out-of-scope.md)) like any message.
- **Logs.** IDs, status and durations only. Never transcript text.
- **Routes table.** These routes are added to the [#25](25-chat-endpoint.md) routes table by reference.

## Testing Decisions

- **Seam 2 (Lambda handlers)** with `aws-sdk-client-mock`:
  - another producer's conversation returns 404 on every voice route;
  - a closed conversation returns 409;
  - the POST form's policy fixes the conversation's prefix, the allowed types and the 5 MB limit;
  - the completion worker stores the transcript and deletes the audio and output, even when no client is polling;
  - a failed job is marked `failed` and its audio deleted;
  - cancel before a job starts deletes the audio, and no job is started afterwards;
  - cancel while a job runs marks the item `cancelled`, and the worker then deletes the output without storing a transcript;
  - the first `GET` after completion returns the transcript and removes it; a second `GET` returns `delivered` with no transcript;
  - a `GET` after `expires_at` returns 404, even before TTL has removed the item;
  - no transcript text is logged.
- **Component tests:**
  - the transcript lands in the message box and is not sent automatically;
  - cancel discards the recording;
  - the record control works by keyboard and announces its state.

## Out of Scope

- Real-time (streaming) transcription
- Keeping audio for review or training
- Voice replies from FEX

## Further Notes

### Decisions made while writing this spec

- Batch transcription rather than streaming, so no browser credentials or WebSocket handling are needed. The cost is a short wait after recording.
- Audio and raw transcripts are deleted as soon as the transcript is returned.
- The producer reviews and sends the transcript; it is never sent automatically.
