# Spec: Chat endpoint (#25)

Status: approved for build, 2026-11-04.

## Problem Statement

The web chat needs a way to reach FEX. Three problems make a plain request-and-response endpoint unsafe and slow:

- **Ownership.** If the browser chooses the conversation ID, producer A can send producer B's ID and continue B's conversation, including its history.
- **Latency.** A turn that retrieves data and writes a cited answer can take 10 to 30 seconds or more. API Gateway's HTTP API cuts requests off at about 30 seconds and cannot stream.
- **Resuming.** Conversations can now be resumed. Producers need to find their own conversations, and nobody else should be able to.

## Solution

An API Gateway REST API fronts TypeScript Lambda handlers.

- **Streaming.** Turns stream over Lambda response streaming: intake and playback text as it is written, and the answer claim by claim as each claim passes the citation check ([#13 spec](13-conversation-steps.md)).
- **Server-owned IDs.** The server creates every conversation ID and records its owner, and checks that owner on every request.
- **One turn at a time.** Each conversation accepts one turn at a time.
- **Idle cleanup.** A scheduled job closes idle conversations.

## User Stories

1. As a producer, I want FEX's questions to appear as they are written and each checked insight to appear as soon as it is ready, so that the chat feels responsive.
2. As a producer, I want long answers to arrive without a timeout, so that a thorough answer is not lost.
3. As a producer, I want my button choices sent separately from my typed messages, so that a choice is never misread.
4. As a producer, I want a list of my conversations, newest first, showing open or closed, so that I can find one to resume.
5. As a producer, I want to reopen an open conversation with its history, step and buttons, so that I can continue where I left off.
6. As a producer, I want to read a closed conversation but not change it, so that I can look back safely.
7. As a producer, I want a clear message if I double-send while FEX is answering, so that the conversation does not get confused.
8. As a producer, I want a readable error if something fails mid-answer, so that I know to try again.
9. As a producer, I want nobody else able to see or continue my conversations, even with the conversation ID, so that my account stays private.
10. As an FTUSA engineer, I want conversation IDs created only by the server, so that IDs cannot be chosen into someone else's conversation.
11. As an FTUSA engineer, I want another producer's conversation to get the same response as a missing one, so that the API does not reveal which IDs exist.
12. As an FTUSA engineer, I want only the chat API's functions able to invoke the agent runtime, so that ownership checks cannot be bypassed.
13. As an FTUSA engineer, I want idle conversations closed automatically, so that their records become final and reviewable.
14. As an FTUSA engineer, I want Lambda logs without message text, so that producers' words do not spread into logs.
15. As a tester, I want a deployed smoke test of one conversation, so that wiring problems show up before the demo.

## Implementation Decisions

### Shape

- **API type:** an API Gateway REST API, not HTTP API. Start, message and action routes use Lambda response streaming. The other routes use normal proxy integration.
- **Handlers:** TypeScript on the Node.js 24 Lambda runtime (`nodejs24.x`), using Lambda Powertools for logging and tracing.
- **Runtime version (decided 2026-11-04):** the technical environment document says Node 20.x, but Lambda deprecated it on 2026-04-30. Node 24 is supported until 2028-04-30, past FTUSA's 2027 workshops and launch. The api package's Node engine and types move to 24.
- **Supersedes the existing stubs:** they use HTTP API event types and a single chat route. That includes the TypeScript write-back handler, since write-back runs in Python ([#26 spec](26-write-back.md)).
- **Timeouts:** the integration and Lambda timeout on streaming routes is 5 minutes.
- **CORS:** allows only the web app's CloudFront origin.

### Routes (shared contract owned here)

| Method and path | Streams | Purpose |
|---|---|---|
| `POST /conversations` | yes | Creates a conversation owned by the caller and streams the agent `start` turn |
| `POST /conversations/{id}/messages` | yes | Body `{ "text": string }`, at most 4,000 characters (agent `message`) |
| `POST /conversations/{id}/actions` | yes | Body `{ "action": string, "args": object }` (agent `action`); actions are defined in the [#13 spec](13-conversation-steps.md) |
| `GET /conversations/{id}` | no | History, current step and allowed actions (agent `resume`), for open or closed conversations |
| `GET /conversations` | no | The caller's conversations, newest first: ID, created time, open or closed |

- **Identity:** every route resolves the caller first through the identity-resolution function ([#11 spec](11-identity.md)).
- **Unknown fields:** bodies with unknown fields, including any producer ID or conversation ID, get 400.
- **Other errors:**
  - 404: the conversation is missing or owned by someone else. Both cases get the same response.
  - 409: the conversation is closed (messages and actions only), or a turn is in progress.

### Stream format (shared contract owned here)

- **Format:** newline-delimited JSON (`application/x-ndjson`), one event per line.
- **Pass-through:** the agent's events from the [#13 spec](13-conversation-steps.md) are passed through unchanged.
- **Added by the handler:**
  - a leading `conversation` event with the new ID on `POST /conversations`;
  - `error` then `done` if the agent call fails mid-stream.

### Conversation ownership (shared contract owned here)

- **Table:** a conversations table, partition key `conversation_id`. It holds `producer_id`, `created_at`, `status` (`open` or `closed`), `closed_at`, `last_activity_at`, and the turn lock. A secondary index on `producer_id` and `created_at` serves the list route.
- **Creating:** the conversation ID is a server-generated random UUID v4, which is also long enough for an AgentCore runtime session ID.
- **Checking:** every `{id}` route loads the conversation and compares its `producer_id` to the resolved caller before anything else.
- **Closing:** when the stream carries `step: closed`, the handler sets `status` to `closed` and records `closed_at`.
- **Who writes:** only the chat handlers and the sweep write to this table. The agent runtime has no access to it.

### Calling the agent

- **Invocation:** handlers call AgentCore `InvokeAgentRuntime` with the runtime session ID set to the conversation ID. The payload carries the request kind, `producerId`, `conversationId`, and the text or action.
- **Restricted access:** only the chat handlers' role and the sweep's role may invoke the runtime.

### Turn lock (shared contract owned here)

- **Taking it:** before invoking the agent, the handler takes a lock with a conditional update on the conversation item. The update succeeds only if no unexpired lock exists, and sets an expiry slightly longer than the 5-minute timeout.
- **Releasing it:** the lock is released only after the agent call has finished, whether it succeeded or failed. If the handler itself crashes, the lock's expiry frees it.
- **Busy:** a second request while the lock is held gets 409.
- **Reads:** `GET` routes take no lock. They return the last saved state.

### Activity time

`last_activity_at` is set when `POST /conversations`, a message or an action is accepted. `GET` routes and the sweep never change it.

### Inactivity sweep (shared contract owned here)

- **Schedule:** a scheduled Lambda runs every 15 minutes.
- **What it does:**
  - It finds open conversations whose `last_activity_at` is older than the inactivity period, or whose `created_at` is older than the maximum conversation lifetime.
  - For each one, it takes the turn lock and re-checks the condition.
  - It then sends an `auto_close` request ([#13 spec](13-conversation-steps.md)) with reason `inactivity` or `max_lifetime`, and marks the conversation closed when the stream reports `step: closed`.
- **Reconciliation:** for open conversations that are not idle, the sweep sends `resume`. If the agent reports step `closed` (for example, because a stream was cut off after the agent closed the conversation), the sweep marks the conversation closed.

### Logging

- **Contents:** logs carry the conversation ID, producer ID, route, status, step changes and timings. They never carry message or answer text.

## Testing Decisions

- **Seam 2 (Lambda handlers),** per the [specs README](README.md).
  - **Setup:** tests use Vitest; the api package has no test runner yet, so the first PR adds it. Streaming handlers write into a captured fake response stream.
  - **Covered:**
    - a body with a producer ID or conversation ID rejected;
    - another producer's conversation returning the same 404 as a missing one;
    - a closed conversation returning 409 for messages and actions;
    - a concurrent turn returning 409, and the lock released after success and after failure;
    - agent events passed through in order;
    - a mid-stream failure ending with `error` then `done`;
    - `step: closed` marking the conversation closed;
    - the list returning only the caller's conversations;
    - the sweep closing idle conversations and conversations past the maximum lifetime (even if active), and skipping an idle one that became active before it took the lock;
    - the sweep marking a conversation closed when `resume` reports `closed`;
    - `GET` routes leaving `last_activity_at` unchanged;
    - `claim` events passed through as they arrive;
    - no message text in logs.
- **Seam 3 (deployed smoke test):** start, messages, confirm, consent and feedback, a resume, and a request as a different producer returning 404.

## Out of Scope

- Review, analytics and "your record" routes ([#27](27-review-api.md), [#29](29-analytics-api.md), [#32](32-your-record.md))
- The web UI beyond the routes and stream format
- Production identity, WAF and rate limiting beyond API Gateway defaults

## Further Notes

### Not decided (do not build or assume)

- The inactivity period and the maximum conversation lifetime
- The deployed sign-in stand-in ([#11 spec](11-identity.md))
