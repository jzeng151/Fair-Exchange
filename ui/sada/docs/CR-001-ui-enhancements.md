# CR-001 — UI Enhancements (Enhancements 1)

**Status:** In progress
**Author:** sada-narayanappa
**Source:** `SDD.md` → "Enhancements 1"
**Scope:** `/workshop/ui/sada` (Django PoC). All data fictitious; mock today, Bedrock-ready.

## Background
The PoC chat UI (persona picker, location/weather, voice, multilingual, guardrails) is in place.
This CR adds the "Enhancements 1" capabilities and fixes two defects.

## Changes

### Fixes
- **F1 — "Something went wrong" on send.** Replace the brittle failure path with real, varied mock
  responses that read like a live assistant. Keep the optional Amazon Bedrock path (`USE_BEDROCK=1`),
  and fall back to richer mock text rather than an error.
- **F2 — Delete a question.** Each user turn (and its answer) can be removed from the transcript.
- **F3 — New chat.** A clear "Start new chat" control resets the transcript and conversation id.

### Enhancements
- **E1 — Attachments.** Attach documents, text snippets, and pictures to a message. Thumbnails/chips
  shown in the composer and the sent message. (PoC: client-side preview + server acknowledges; no storage.)
- **E2 — History by period.** Group interaction history by Today / This week / This month / This quarter,
  with a period switcher.
- **E3 — Reports from history.** Generate a simple report (summary, top concerns/tags, timeline,
  sentiment mix) from the current chat history; downloadable as a text/markdown file.
- **E4 — Demographics & trends.** A panel showing demographic context and trending concerns relevant to
  the persona's region/product (fictitious, aggregated).
- **E5 — Sentiment + follow-ups.** Each answer carries a sentiment read and offers follow-on questions.
- **E6 — Share-data permission.** A clear consent control to share the conversation's data, with an
  explicit, reversible opt-in (mirrors the project's consent principle; a decline is a valid outcome).
- **E7 — Shared-data stats + points.** Once sharing is on, show how much has been shared and points
  earned, as a light gamified summary.

## Non-goals (this CR)
- Durable storage of attachments or real file uploads to S3.
- Real demographic/trend data feeds (mocked, shaped for later wiring).
- Authentication (PoC stays sign-on free).

## Design principles kept
- Suggestion tone, never commanding; decision handed back to the user.
- Every answer carries citations; PII flagged, never redacted.
- `.env` holds secrets and stays gitignored.

## Acceptance
- Sending a message always yields a real-looking, grounded answer (never "Something went wrong").
- A question can be deleted; a new chat can be started.
- Attachments can be added and appear on the sent message.
- History groups by period; a report can be generated and downloaded.
- Demographics/trends, sentiment + follow-ups, share-consent, and shared-stats/points are all visible
  and interactive in the chat view.
