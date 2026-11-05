# Spec: Spanish exchange and bilingual record (#22)

Status: approved for build, 2026-11-04.

## Problem Statement

The 2027 workshops are in Peru and Honduras, so a full exchange in Spanish is a must-have. FTUSA reviewers need the producer's words in Spanish and in English. If language handling is ad hoc, records end up with mixed languages, untranslated summaries, or tags in different languages.

## Solution

FEX identifies the producer's language during intake and replies in it for the whole conversation. The record keeps the summary in the producer's own words and language, plus an English summary. Tags always use the English values from the 11-tag set.

## User Stories

1. As a Spanish-speaking producer, I want the whole conversation in Spanish, so that I can use it without translation.
2. As a Spanish-speaking producer, I want button labels in Spanish, so that I understand every choice.
3. As a producer, I want FEX to keep replying in my language even when citing English-language sources, so that the answer is readable.
4. As an FTUSA reviewer, I want the summary in the producer's own words and language plus an English version, so that I can review Spanish conversations.
5. As an FTUSA analyst, I want tags stored as the same English values regardless of language, so that conversations group correctly.

## Implementation Decisions

### Language code rules (shared contract owned here)

- **Identifying the language.** The conversation language is identified during intake and stored as an ISO 639-1 code (`en`, `es`, and `fr` with [#24](24-french-exchange.md)). It is the language the producer writes in.
- **Replies.** FEX replies in that language, including playback and the answer. Citations keep the source's original names.
- **Opening language.** The opening question uses the language in the producer's profile if it has one, otherwise English. Once intake identifies the producer's language, FEX switches to it.
- **Buttons.** The agent sends action names only. The client supplies labels in the producer's language, using the `language` field on `step` and `actions` events and on the resume response ([#13 spec](13-conversation-steps.md)).
- **Fixed text.** The answer's opening line, limited-evidence notice and closing hand-back exist in English, Spanish and French ([#13 spec](13-conversation-steps.md), [#24](24-french-exchange.md)).
- **Record fields:**
  - `summary_original` is in the producer's language.
  - `summary_english` is required for any non-English conversation; the existing schema already enforces this.
  - Both come from the confirmed playback ([#26 spec](26-write-back.md)).
  - `tags` always uses the English values of the 11-tag set.
- **Conversation.** Claude handles Spanish (and French, [#24](24-french-exchange.md)) directly: what FEX says to the producer is never machine-translated.
- **Reviewer translation (changed 2026-11-04: Amazon Translate).** For a non-English conversation, `summary_english` is **Amazon Translate's** translation of `summary_original` (source: the conversation language, target: `en`), made when the playback is confirmed. Reviewers then check a translation from a dedicated service rather than a model paraphrase, and FTUSA already uses Translate in its ETL (technical environment). The model's own English summary is still requested and is the **fallback**: if the Translate call fails, `summary_english` is the model's text and the decision log records `translation_fallback`, so the record never lacks an English summary. Demo mode (no AWS) uses the model's English summary. The agent runtime gets `translate:TranslateText`.
  - This replaces the earlier rule (no Amazon Translate in the loop, from the vision document's assumption) for reviewer-facing English only; the conversation itself still has no translation step.

## Testing Decisions

- **Seam 1 (agent entrypoint),** with scripted Spanish model output, per the [specs README](README.md). Cases:
  - `language` stored as `es`;
  - `step` and `actions` events and the resume response carrying `es` once identified;
  - fixed answer text in Spanish;
  - both summaries present;
  - tags using English values;
  - a record without `summary_english` for a Spanish conversation rejected;
  - `summary_english` for a Spanish conversation is the translator's output for `summary_original`, with source `es` and target `en`;
  - a failing translator falls back to the model's English summary and logs `translation_fallback`;
  - an English conversation calls no translator.
- **Evals:** one scripted Spanish scenario runs end to end with real Bedrock. It has the same record quality checks as the English scenarios.

## Out of Scope

- French, added by the [#24 spec](24-french-exchange.md) when built, and other languages
- Translating the producer's own words inside `summary_original`
