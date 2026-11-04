# Spec: Identity contract (#11)

Status: approved for build (contract only), 2026-11-04.

## Problem Statement

Every data tool, the memory store and the record all trust the producer ID they receive. If the browser can supply that ID, any tester can act as any producer. How callers sign in is not decided yet, but the rest of the system needs to be built now without depending on that choice.

## Solution

All handlers get the caller's identity from one identity-resolution function. Nothing else in the system reads identity from a request. When the sign-in method is decided, only this function changes.

## User Stories

1. As a producer, I want to be refused if I try to act as another producer by editing a request, so that nobody can read my data that way.
2. As an FTUSA engineer, I want identity resolution behind one function, so that whichever sign-in FTUSA chooses replaces it without touching handlers.
3. As an FTUSA engineer, I want handler tests to run with a fake resolver, so that the API can be built before sign-in is decided.

## Implementation Decisions

### Identity-resolution function (shared contract owned here)

- **Input and output.** It takes the incoming API request and returns the caller's identity, or rejects the request (the handler returns 401). The identity has:
  - `user_id`;
  - `roles`, any of `producer`, `reviewer` and `admin`;
  - `producer_id`, present only with the `producer` role.
- **Route access (added 2026-11-04 with the review and analytics specs):**
  - chat routes and `GET /me/records` require `producer` ([#25 spec](25-chat-endpoint.md), [#32 spec](32-your-record.md));
  - review routes require `reviewer` ([#27 spec](27-review-api.md));
  - analytics requires `admin` ([#29 spec](29-analytics-api.md)).
  - A missing role returns 403.
- **`GET /me`.** Returns the caller's `user_id` and `roles`, so the web app can show the right views. Any identified caller may use it.
- **Never from the request.** No handler reads a producer ID from the body, path, query string or a client-set header. Request bodies containing a producer ID are rejected with 400 ([#25 spec](25-chat-endpoint.md)).
- **Agent side.** The producer ID it returns is the only producer ID passed to the agent. Tools, memory and records use it from the request context.
- **Tests.** A fake resolver returns a fixed identity or rejects.

## Testing Decisions

Seam 2 (Lambda handlers), per the [specs README](README.md). Cases:
- a rejected identity returning 401 on every route;
- a valid identity without the route's role returning 403;
- a producer ID in the body rejected with 400;
- the resolved ID, and not any ID in the request, reaching the agent call.

## Out of Scope

- Production identity (Okta), which is FTUSA's

## Further Notes

### Not decided (do not build or assume)

- How callers sign in, and the deployed stand-in for it. The deployed smoke test and the demo need this before the chat endpoint can run end to end.
