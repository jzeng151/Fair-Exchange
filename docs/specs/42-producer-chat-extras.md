# Spec: Listen, photo and document notes, and clearer answers in the live chat (#169)

Status: draft, 2026-11-05. Brings the features tested in the Django sample UI (`ui/sada/`, #166, #167) into the Vue live chat, then removes the Django UI, so there is one producer front end (decided 2026-11-05 with the repo owner). Supersedes PR #168.

## Problem Statement

The Nov 5 demo ran on the Django sample UI, which added features the Vue live chat (`web/`, [#25](25-chat-endpoint.md)) does not have:
- answers read aloud;
- photos and documents a producer can attach;
- numbered citations;
- a plain explanation of each consent choice;
- the brand palette from design.fairtradecertified.org.

Keeping two producer front ends means fixing everything twice. These features move to the Vue site and its TypeScript API, under the same rules as voice notes ([#41](41-voice-notes.md)):
- the producer sees and controls what is sent;
- ownership and scope checks apply;
- PII is flagged, not lost;
- uploaded files don't pile up as a new store of producer data.

## Solution

1. **Listen.** Each FEX reply and each answer card gets a Listen button. Amazon Polly reads it aloud with a neural voice in the conversation's language. Nothing is stored.
2. **Photo and document notes.** A paperclip button lets the producer attach one photo or PDF. Claude on Amazon Bedrock describes what it shows in one or two sentences, and the file is deleted. The description is placed in the message box for the producer to review and edit, exactly like a voice transcript. Nothing reaches FEX until the producer presses send, and the sent text is an ordinary message.
3. **Clearer answers.**
   - Answer cards are numbered [1], [2], and so on.
   - Sources from WRI Aqueduct are marked as listed in the TNFD Tools Catalogue.
   - The consent question explains who can see each choice.
4. **Brand.** The site uses the Fair Trade USA brand palette on a cream background.

## User Stories

1. As a producer who reads with difficulty, I want to hear FEX's replies, so that I can follow the conversation.
2. As a producer, I want to share a photo of my crop or a document, so that I can show the problem instead of describing it.
3. As a producer, I want to see and edit what FEX will receive from my photo before it is sent, so that only what I mean to share is sent.
4. As a producer, I want to know who can see my conversation under each consent choice, so that my consent is informed.
5. As a producer or reviewer, I want each fact numbered with its source, so that I can match facts to sources.
6. As an FTUSA engineer, I want attached files deleted as soon as they are read, so that attachments don't create a new store of producer files.
7. As an FTUSA engineer, I want the new routes to follow the same ownership checks as chat, so that nobody can read files into, or hear text for, someone else's conversation.

## Implementation Decisions

### Listen (Amazon Polly)

This changes [#41](41-voice-notes.md)'s "Out of Scope: voice replies from FEX" (decided 2026-11-05).

- **Route.** `POST /conversations/{id}/speech`. It is on the same REST API, `producer` role, with the ownership check from [#25](25-chat-endpoint.md). The conversation may be open or closed, so earlier replies can still be heard.
- **Request.**
  - The body is `{ "text": string }`, with no other keys.
  - `text` is 1 to 1,500 characters, counted in UTF-16 units like the chat API.
  - Anything else returns 400.
- **Voice.** Chosen by the server from the conversation's stored language, never from the request: `en` Joanna (en-US), `es` Lupe (es-US), `fr` Léa (fr-FR). All use the neural engine. Any other language uses `en`.
- **Response.** `200 { "content_type": "audio/mpeg", "audio": "<base64 MP3>" }`. The audio is not stored anywhere.
- **Abuse limit.** The route only reads text aloud; it doesn't check that the text came from FEX. The 1,500-character cap, the producer sign-in and the API's existing throttling bound the cost. Neural Polly is about $16 per million characters.
- **Client.**
  - A Listen button on each FEX text bubble and each answer card reads that item. Starting one stops any other.
  - If the route fails, the client falls back to the browser's speech synthesis in the conversation's language. If that is unavailable too, a notice says so.
  - The button works by keyboard and announces whether it is playing.
- **Role.** `polly:SynthesizeSpeech` on `*` (Polly has no resource-level permissions), read on the conversations table, and decrypt on the data key.
- **Logs.** Conversation ID, character count, voice and duration only. Never the text.

### Photo and document notes (Claude on Amazon Bedrock)

- **Routes.** These are on the same REST API, `producer` role, with the ownership check from [#25](25-chat-endpoint.md). The conversation must be open.

| Method and path | Purpose |
|---|---|
| `POST /conversations/{id}/attachments` | Returns `201 { attachment_id, upload: { url, fields }, expires_at }`, like voice. Body `{ "content_type": ... }`, one of `image/jpeg`, `image/png`, `image/webp` or `application/pdf`. Creates an `attachment_id` (random UUID) and returns a pre-signed POST form, valid for 5 minutes. Its policy fixes the key to `attachments/{conversation_id}/{attachment_id}`, fixes `Content-Type` to the requested type, requires KMS encryption with the data key, and sets `content-length-range` to at most 3.75 MB (Bedrock's image limit). |
| `POST /conversations/{id}/attachments/{attachment_id}/read` | Checks the uploaded object (it exists, its size is within the limit, its type is allowed) and sends it to Claude with the prompt below. It deletes the object whether or not the call succeeds, and returns `200 { "description": string }`. A second read returns 404, because the file is gone. |
| `DELETE /conversations/{id}/attachments/{attachment_id}` | Cancels: deletes the object if it is still there. Returns 200 whether or not it was there. Like the other attachment routes it needs an open conversation (409 otherwise); a file left on a closed conversation is removed by the bucket's 1-day lifecycle rule. |

- **No attachment table.** The key carries the conversation ID, so the route's ownership check covers it. The content type comes from the object, which the upload policy fixed.
- **Model.** The small model (`SMALL_MODEL`, Claude Haiku) through its US inference profile, with the Bedrock Converse API: an `image` or `document` block plus a text prompt, and at most 200 output tokens.
- **Prompt.** "A Fair Trade producer attached this file to describe a challenge on their farm or in their organization. In one or two short sentences, state factually what it shows that is relevant to farming, water, crops, land, labour or prices. Do not name or describe any person, and do not include names, phone numbers, IDs or addresses. If nothing relevant is visible, say so. Reply in {conversation language}."
- **Client.**
  - A paperclip button next to the microphone opens a file picker that accepts the four types. The client checks the size first.
  - While the file is read, the button shows a "reading" state.
  - The description is added to the message box as `[Photo: …]` or `[Document: …]` for review. It is never sent automatically.
  - One attachment at a time.
  - If reading fails, a notice says so and the producer can type instead.
- **Storage.**
  - Files go to the existing voice bucket ([#41](41-voice-notes.md)) under a new `attachments/` prefix. That bucket is already KMS-encrypted, has public access blocked, allows `POST` CORS only from the web app's origin, and deletes objects after 1 day as a backstop.
  - The read route deletes the file right after reading.
  - The description is not stored by the route. It is kept only if the producer sends it as a message, and is then treated like any message.
- **PII and scope.**
  - The prompt asks the model not to repeat personal details, but the safety net is the normal message path. The sent text gets the PII check ([#20](20-pii-flagging.md)) and the out-of-scope check ([#21](21-out-of-scope.md)) like any producer message.
  - No Guardrail is applied to the description itself, because it reaches FEX only through that path.
- **Role.**
  - Read, put and delete on `attachments/*` in the voice bucket.
  - `s3:ListBucket` on the voice bucket. This is the one bucket-level permission: without it, S3 answers a missing file with 403 instead of 404, and "a second read returns 404" depends on that.
  - Encrypt and decrypt on the data key.
  - Read on the conversations table.
  - `bedrock:InvokeModel` on the small model's US inference profile and the US-region foundation models behind it, the same ARN pattern as the agent runtime.
- **Logs.** IDs, content type, size and duration only. Never the description or file contents.
- **Routes table.** These routes are added to the [#25](25-chat-endpoint.md) routes table by reference.

### Clearer answers (web only)

- **Numbered citations.**
  - Answer cards are numbered in the order they arrive, across both sections, starting at 1.
  - Each card's source line starts with its number, e.g. `[1] Source: WRI Aqueduct 4.0 … · Standard: APS 2.4.2.a`.
  - Numbers restart with each new answer, for example after "Change what I said".
- **TNFD note.** A citation whose source contains "WRI Aqueduct" gets "· Listed in the TNFD Tools Catalogue" (es: "Incluido en el catálogo de herramientas de la TNFD", fr: "Répertorié dans le catalogue d'outils de la TNFD"). The wording says "listed", not "approved" or "endorsed", because the catalogue states that inclusion does not imply endorsement.
- **Consent explainer.** Under the consent question, three short lines in the conversation language:
  - FTUSA only: the Fair Trade USA team can read it to improve support.
  - Shared: other producers and partners only ever see it combined with others, never with your name.
  - Don't keep: no summary is saved for Fair Trade USA, only that the producer said no. The conversation itself is deleted automatically after 7 days (the AgentCore Memory event expiry, `MEMORY_EVENT_EXPIRY_DAYS`). The same correction applies to the message shown after declining, which used to say "nothing from this conversation is kept" (changed 2026-11-05 in review).

  These lines match what [#19](19-consent-and-decline.md) and [#29](29-analytics-api.md) already guarantee and promise nothing more.

### Brand (web only)

This changes the tokens in `web/src/styles/tokens.css`, which came from the FTUSA UI/UX specification v1.1 (decided 2026-11-05: follow design.fairtradecertified.org).
- **Canvas:** cream `#F7F2E8`.
- **Primary:** Indigo `#313D7F`, used for buttons and links.
- **Accents:** Cyan `#44AEC8`, Green `#93D73B` and Amber `#ECCA52`.
- **Text:** Dark Grey `#39373A`.
- **Status colours** (error, success, warning) are unchanged.
- **Contrast:** text and controls keep at least WCAG AA contrast on the new canvas, and the tests check the main pairs.
- **Header:** reads "Fair Exchange for Fair Trade USA". "For", not "by", because this is a Team 60 prototype, not an FTUSA publication.

### Carried over from PR #168 (not specific to the Django UI)

- **Intake prompt** (`agent/src/fex/conversation/engine.py`): FEX never mentions internal steps or words like "intake", "playback" or "step". If asked for data or advice during intake, it says warmly that it will look up the data once it understands the situation, then asks the next question. This was found in the Nov 5 demo, where FEX told a producer "In this intake I am only gathering the details…".
- **`infra/deploy.sh`:** an opt-in `SKIP_TRANSACTION_SEARCH=1` for accounts where X-Ray Transaction Search can't be turned on, such as workshop accounts. Without it, behaviour is unchanged. AgentCore traces are then missing from CloudWatch Transaction Search in that account, and nothing else changes.

### Removing the Django sample UI

- Delete `ui/sada/` once the Vue chat has every feature above.
- Its separate deployment (`FairExchangeSampleUi`, deployed by `ui/sada/deploy/deploy.sh`) is not part of `infra/deploy.sh`. Any account that deployed it removes it with `aws cloudformation delete-stack --stack-name FairExchangeSampleUi` when it is no longer needed. Deleting the folder doesn't remove a running copy.

## Testing Decisions

- **Seam 2 (Lambda handlers)** with `aws-sdk-client-mock`:
  - another producer's conversation returns 404 on every new route;
  - the attachment routes return 409 on a closed conversation; speech works on open and closed conversations;
  - speech picks the voice from the stored conversation language and ignores any language in the request;
  - speech rejects empty text, text over 1,500 UTF-16 units and unknown keys;
  - the attachment POST form's policy fixes the conversation's prefix, the requested type, KMS encryption and the 3.75 MB limit;
  - read sends an image or document block and returns the description;
  - read deletes the object even when Bedrock fails;
  - a second read returns 404;
  - an object over the limit or with a disallowed type is rejected, and deleted;
  - no text, description or file content is logged.
- **Infra:** `infra/` has no unit-test runner, so CI's type check and `cdk synth` cover it. The PR description lists the synthesized permissions:
  - the speech role has `polly:SynthesizeSpeech`;
  - the attachment role has Bedrock access only on the small model, and S3 access only on `attachments/*`.
- **Component tests:**
  - Listen plays the returned audio and falls back to speech synthesis when the route fails;
  - an attachment's description lands in the message box and is not sent automatically;
  - answer cards are numbered and an Aqueduct source shows the TNFD note;
  - the consent explainer shows in the conversation language.
- **Deployed integration check:** after `infra/deploy.sh`, Listen plays in English and Spanish, and a photo of a crop returns a description, after which the object is gone from the bucket.

## Out of Scope

- Ending the conversation automatically after feedback. [#23](23-feedback-capture.md) keeps the feedback step open so a misclick can be fixed, and the Vue chat already collapses the answered question.
- A language menu with Amazon Translate. FEX already replies in the producer's language, and voice notes already get an English translation ([#41](41-voice-notes.md)).
- More than one attachment per message, other file types, and keeping files for review.
- Deleting already-deployed copies of the Django UI (see "Removing the Django sample UI").

## Further Notes

### Deployment

- Merging deploys only the website (the `deploy` job in `.github/workflows/ci.yml`).
- The new routes need `infra/deploy.sh` run by the account owner.
- Until then, Listen falls back to browser speech, and the paperclip shows "not available yet" when the route is missing.

### Decisions made while writing this spec

- The attachment description goes to the message box for review instead of straight to FEX, matching voice notes.
- Attachments reuse the voice bucket with a new prefix, instead of a new bucket.
- There is no attachment table: the file itself is the state, and it is deleted after one read.
- Listen returns base64 audio in JSON instead of binary, so no API Gateway binary media settings are needed.
