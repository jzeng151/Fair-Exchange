# Spec: Persistent conversation memory (#59)

Status: approved for build, 2026-11-04. Revised 2026-11-04 after review. The client asked for persistent conversation memory on 2026-11-04.

## Problem Statement

A producer who closes the browser loses the conversation. FEX also knows nothing about earlier conversations, so the producer repeats their situation every time. The client wants both fixed:
- a producer can resume an unfinished conversation later;
- FEX remembers what a producer said in earlier, separate conversations.

Memory is also a new way to leak data across producers, and a way for text a producer declined to share to resurface. It must follow the same scope rule as the data tools.

## Solution

Conversations are stored in Amazon Bedrock AgentCore Memory, keyed by the producer ID and conversation ID that the chat API supplies. Short-term memory holds each conversation's messages and state, so it can be resumed. Long-term memory extracts summaries and facts per producer.

Recall of earlier conversations goes through one eligibility function. Recall stays switched off until the decline policy is decided, so declined text cannot resurface in a later record.

## User Stories

1. As a producer, I want to close my browser and later resume the same conversation where I left off, so that I can check something with my committee first.
2. As a producer, when I resume, I want to see earlier messages and the buttons for the current step, so that I know where I am.
3. As a producer starting a new conversation, I want FEX to remember what I told it before, so that I do not repeat my situation from scratch.
4. As a producer, I want FEX to use what it remembers only to understand my situation, not as a cited fact, so that every fact it gives me is traceable.
5. As a producer, I want anything I declined to share never to resurface in a later conversation or record, so that my choice holds over time.
6. As a producer, I want FEX never to recall anything another producer said, so that my conversations stay mine.
7. As an FTUSA engineer, I want memory keyed by the producer ID from the API, never by anything the model or producer types, so that memory follows the scope rule.
8. As an FTUSA engineer, I want the agent rebuilt from memory on every request, so that a recycled runtime does not lose a conversation.
9. As an FTUSA engineer, I want retention periods to be configuration values, so that they can follow FTUSA's privacy policy without code changes.

## Implementation Decisions

- **Store.** AgentCore Memory, connected through the Strands AgentCore Memory session manager.
- **Keys.** The actor ID is the producer ID, and the session ID is the conversation ID. Both come from the request context the chat API sets. Neither ever comes from model output or producer text.
- **Short-term memory (resume).**
  - Each conversation's messages and conversation state, as listed in the [#13 spec](13-conversation-steps.md), are stored.
  - The agent is rebuilt from memory on every request and never relies on in-process state surviving between requests.
  - `resume` returns history, step and allowed actions from memory.
- **Long-term memory.** The summarization and semantic strategies are enabled. Namespaces are templated on the actor ID, so each producer's memories sit under their own namespace. Any retrieval reads only the calling producer's namespace, which is built in code from the request context.
- **Recall eligibility.**
  - Recall into intake and playback goes through one eligibility function that decides which long-term memories may be used.
  - Until the decline policy is decided, this function returns nothing, so recall is built but switched off.
  - When switched on, recalled context feeds intake and playback only. It is never a citable source; insights and peer examples come only from the data tools and the citation check.
- **Retention.**
  - The short-term event expiry and any long-term record expiry are configuration values. AgentCore allows 3 to 365 days for events. Long-term records do not expire unless a time-to-live of at least 31 days is set.
  - Whatever values are chosen, the event expiry must be longer than the maximum conversation lifetime ([#13 spec](13-conversation-steps.md)). The lifetime counts from the conversation's start, so every message of an open conversation survives until it closes, however active it stays. The agent refuses to start if the configuration breaks this rule.
- **Deletion function.**
  - It deletes one conversation's short-term events.
  - Whether long-term records can be traced to a single conversation, given that long-term memory consolidates across conversations, is a spike check (below). Until that check passes, the function covers short-term events only, and this spec makes no promise about long-term records.
- **Permissions.** The agent runtime role gets only the memory permissions it needs on this one memory resource.
- **CDK.** The memory resource is defined in CDK. The construct is alpha, so pin its version.

## Testing Decisions

Seam 1 (agent entrypoint), per the [specs README](README.md), with an in-memory memory stand-in behind the same interface. Cases:
- resume after the agent object is discarded, returning the same history, step, allowed actions and state;
- a long-term read for producer A never returning producer B's memories, even when B's text mentions A;
- the eligibility function returning nothing while recall is switched off;
- the deletion function removing one conversation's short-term events and no other conversation's;
- a configuration whose event expiry is not longer than the maximum conversation lifetime rejected at startup.

Evals run against real AgentCore Memory.

**Spike checks (#4):**
- The session manager persists the conversation state as well as messages.
- Whether long-term records can be traced to the conversation they came from.
- Whether AgentCore traces capture message content.

## Out of Scope

- What the record stores ([#26 spec](26-write-back.md))
- Sharing memory across producers in any form

## Further Notes

### Not decided (do not build or assume)

- The retention values for short-term events and long-term records
- When the deletion function is called, including what happens to stored conversation text when a producer declines
- Which long-term memories are eligible for recall (this is why recall is switched off)

### Change to an existing requirement

The vision document's Journey 2 says a decline stores no conversation content. With persistent memory (client request, 2026-11-04), conversation text is stored while the conversation runs. The declined record still has no narrative content (the record schema enforces this). What happens to the stored conversation text is listed above as not decided.

### Build notes (as implemented, #59)

These record the concrete choices the build made within the decisions above. They do not change any "Not decided" item.

- **StateStore.** `AgentCoreMemoryStateStore` (agent `fex.conversation.memory`) implements the existing `StateStore` Protocol (#13). Each saved `ConversationState` is one short-term event under actor = producer ID, session = conversation ID; the newest event is the current state. The state's `revision` field carries optimistic concurrency, so a stale request raises `StateConflict` rather than overwriting newer state, exactly as `InMemoryStateStore` does. `resume` reads the latest event, so history, step and allowed actions all come from the stored state.
- **Config.** `FEX_MEMORY_ID` selects the memory-backed store; with it unset the agent uses the in-process store (local runs). `FEX_EVENT_EXPIRY_DAYS` and `FEX_MAX_LIFETIME_MINUTES` are the retention values; both must be set when `FEX_MEMORY_ID` is. The startup check (`RetentionConfig`) refuses to start unless event expiry (3–365 days) is strictly longer than the maximum conversation lifetime.
- **Namespaces.** Long-term namespaces template on the actor ID as `/actor/{actorId}/` (`producer_namespace` in the agent, mirrored by the CDK strategies). Summaries sit one level down, at `/actor/{actorId}/session/{sessionId}/`, because AgentCore keeps summaries per session and requires `{sessionId}` in the summary strategy's namespace (corrected 2026-11-04: `CreateMemory` rejected the actor-only namespace). Retrieval reads only the calling producer's namespace, built in code from the request context.
- **Recall.** `recall_eligibility(actor_id, query)` is the single eligibility seam and returns `[]`, so recall is built but switched off.
- **Deletion.** `delete_conversation(producer_id, conversation_id)` deletes that conversation's short-term events only, and no other conversation's.
- **CDK.** `FexMemory` (infra `lib/memory.ts`) defines one `AWS::BedrockAgentCore::Memory` with the summary and semantic strategies, event expiry 7 days, and `grantAgentAccess(role)` for the scoped runtime permissions. The L1 construct is new, so `aws-cdk-lib` (infra) and the memory client (agent) are pinned together.
