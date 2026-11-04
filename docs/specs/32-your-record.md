# Spec: "Your record" view (#32)

Status: approved for build, 2026-11-04. Should-have: start only once the must-haves are on track.

## Problem Statement

Producers own their data. After they consent, they should be able to see exactly what FTUSA stored about them and under which consent scope, in their own language. They must see only their own records. Changing anything after a conversation closes is outside the chat's rules ([#13](13-conversation-steps.md)).

## Solution

A producer-only route and a view in the existing Vue app. It lists the producer's closed conversations and shows what was stored for each one, with consent scope, time and review status. It is view-only (decided 2026-11-04). A producer who wants to change anything is pointed to FTUSA.

## User Stories

1. As a producer, I want a list of my past conversations with their dates and outcomes, so that I can see what I have shared.
2. As a producer, I want to see the summary stored from each conversation in my language, so that I can check it says what I meant.
3. As a producer, I want to see the challenge tags, and the insights and peer examples I was given with their sources, so that I know what is on record.
4. As a producer, I want to see which consent I gave (FTUSA internal only, or also shared outward) and when, so that I can confirm my choice.
5. As a producer, I want to know if an FTUSA reviewer corrected the summary or tags, so that I'm not surprised by changes.
6. As a producer, I want declined conversations shown as "Not stored: you declined" with the date, so that I can see my decline was respected.
7. As a producer, I want to know how to ask FTUSA for a change, so that I have a way to act on what I see.
8. As a producer, I want to see only my own records, so that my data and others' stay private.

## Implementation Decisions

- **API route.** `GET /me/records`, on the same REST API, TypeScript on Node.js 24, `producer` role required ([#11](11-identity.md)). It returns the caller's records with `closed_at` set, newest first.
- **Records not listed until decided.** Conversations that closed without any consent choice, and records whose consent was cleared by a reopened playback, are not listed. Their outcome is not decided yet ([#13](13-conversation-steps.md), [#19](19-consent-and-decline.md)).
- **What is returned, for each record:**
  - **Completed:**
    - record ID, closed time, language and consent scope with its time;
    - effective summary in the producer's language (the reviewer's version if set, otherwise the agent's), with a `changed_by_reviewer` flag;
    - effective tags, with the same flag;
    - insights, peer examples and earlier answers with citations;
    - feedback;
    - review status.
  - **Declined:** record ID, closed time and `declined`.
  - **Never returned:** the English summary for non-English producers, `pii_*` fields, the decision log, `ai_usage` and reviewer identity.
- **Data access.** A filtered scan of the records table on the caller's producer ID, which is adequate at sandbox scale (same approach as [#27](27-review-api.md)). The producer ID comes only from the identity function.
- **View:**
  - a producer route in the Vue app, labeled in English and Spanish (and French with #24) using the existing UI copy file;
  - tag names shown translated;
  - a list of conversations, and a detail panel showing the fields above;
  - a fixed note, in the producer's language, explaining how to contact FTUSA to ask for a change.
  - There are no edit or delete controls.
- **Logs.** Producer ID, route and status only.

## Testing Decisions

- **Seam 2 (Lambda handler)**, with `aws-sdk-client-mock` and a fake identity resolver:
  - only the caller's records are returned, even when other producers' records exist;
  - non-producers get 403;
  - open records are excluded;
  - declined records return only record ID, closed time and `declined`;
  - records whose outcome is not decided are not listed;
  - `pii_*`, decision log, `ai_usage` and the reviewer identity are never present;
  - `changed_by_reviewer` is set when a reviewer value exists.
- **Component tests (Vitest with Vue Test Utils):**
  - Spanish labels for a Spanish producer;
  - the declined row text;
  - no edit or delete controls;
  - the contact note is shown.
- **Negative scope:** included in [#34](34-negative-scope-tests.md).

## Out of Scope

- Withdrawing consent or deleting records from this view (considered and not chosen on 2026-11-04)
- Open (unfinished) conversations, which are resumed from the chat ([#25](25-chat-endpoint.md))
