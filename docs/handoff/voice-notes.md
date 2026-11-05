# Voice input

The live chat implements the [voice spec](../specs/41-voice-notes.md). The old
`agent/src/fex/voice.py` streaming/local-file prototype is not the deployed path.

## Flow

1. The producer clicks Record voice note. `MediaRecorder` captures WebM/Opus or
   MP4, with a two-minute limit and a 5 MB limit. Stop, cancel, errors and navigation
   release microphone tracks. Typing remains available.
2. `POST /conversations/{id}/voice` accepts `{content_type}` and returns a five-minute
   presigned S3 POST. The server fixes the conversation/object key, size, content
   type and KMS encryption. The browser sends its passcode only to the API.
3. After upload, `POST /conversations/{id}/voice/{voice_id}/transcribe` verifies the
   object and starts a named, retry-safe Transcribe batch job. The job uses the
   server's cached conversation language, or automatic English/Spanish/French
   identification before a language is known. Chat stores only the agent's language
   code in the conversation table under the existing turn lease.
4. EventBridge invokes the completion Lambda on success or failure. It reads the
   result, optionally translates it to English, conditionally saves it, and deletes
   the audio and raw output. Cancellation or expiry prevents transcript storage.
   Translation failure still delivers the original. No browser polling is needed
   for cleanup; duplicate completion is safe.
5. The client polls every two seconds for up to 90 seconds. The first successful
   GET atomically consumes both transcript fields. Later GETs return `delivered`
   without text. The transcript is appended to the editable message box. The
   producer must press Send, after which the normal chat/PII flow applies.
6. DELETE cancels and clears both transcript fields and existing objects. Navigation,
   recording errors and polling timeout also request cancellation. An already
   running Transcribe job finishes, and its worker discards the result.

Every route requires a producer identity, an owned conversation, and an open
conversation. Another producer's conversation/note returns 404; a closed one
returns 409. The worker cannot invoke FEX or write consented records.

## Storage and operations

- `VoiceBucketName`: private KMS bucket, one-day lifecycle backstop for abandoned
  uploads, including uploads repeated with a still-valid form after cancellation.
- `VoiceTableName`: KMS-encrypted temporary table, `voice_id` key and `expires_at`
  TTL. One hour is the access deadline; DynamoDB physical TTL cleanup is asynchronous.
  PITR is disabled so temporary transcripts do not gain a backup retention window.
- `VoiceCompletionFunctionName`: EventBridge completion worker. Logs contain no
  transcript, audio, presigned form or passcode. Unexpected worker failures retry.
- Transcribe assumes a dedicated role scoped to this bucket's `audio/` and
  `transcripts/` prefixes and the KMS key. The route may pass only that role to
  Transcribe. It may start only this stack's voice jobs. The worker may read only
  those jobs and translate text.
  Service trust is restricted to this account and region, following the
  [Transcribe trust policy](https://docs.aws.amazon.com/transcribe/latest/dg/security_iam_id-based-policy-examples.html).
  Both the caller and data role can write the transcript prefix for start validation.
- Deployment is part of `infra/deploy.sh`; no separate manual voice provisioning.

The integration check in `scripts/e2e/voice_smoke.py` accepts a short synthetic
Spanish MP4/WebM recording, creates an isolated test conversation, uploads through
its presigned form, waits for the real EventBridge worker, verifies single delivery,
translation, ownership and object deletion, then removes its test table items.
Do not use a recording containing personal information for this check.
