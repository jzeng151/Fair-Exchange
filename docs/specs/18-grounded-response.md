# Spec: Grounded response with enablement tone (#18)

Status: approved for build, 2026-11-04.

## Problem Statement

The answer is the core thing the producer receives. It must contain:
- what the data shows for their challenge, crop and region;
- what comparable producers did;
- a citation for each, framed to inform their decision rather than direct it.

Generic answers that repeat the same insight for every producer with a shared tag fail the vision's success metrics. So do answers that slip into "you should".

## Solution

The large model writes the answer as a short list of claims from the tool results. Each claim cites a source and a clause the tools returned. Claims are written one per line so each can be checked and streamed as soon as it is complete ([#13 spec](13-conversation-steps.md)). The prompt carries the producer's profile and history, so the answer reflects them.

## User Stories

1. As a producer, I want at least one insight about what the data shows for my challenge, crop and region, so that I learn something about my situation.
2. As a producer, I want at least one example of what a comparable producer did, so that I see options others tried.
3. As a producer, I want each insight and example to cite its source and related standard clause, so that I can trust and check it.
4. As a producer, I want short, plain sentences in my language, so that the answer is easy to read.
5. As a producer, I want the answer to inform rather than instruct, so that the decision stays with me and my committee.
6. As a producer, I want an answer that reflects my own history and profile, so that it is not the same answer everyone gets.
7. As an FTUSA reviewer, I want each claim to stand alone with its citation, so that I can review claims one by one.

## Implementation Decisions

- **Model.** The large model (ADR 0001), configured by model ID.
- **Inputs to the prompt:**
  - the confirmed playback;
  - the profile;
  - all items returned by the four data tools in this `respond` step, including backstopped calls ([#17 spec](17-standards-grounding.md));
  - the conversation language.
- **Output format.** One JSON object per line, shaped `{"section": "insights" | "peer_examples", "claim": <Claim>}`, the same shape as the `claim` event. Code parses each completed line, checks it ([#17 spec](17-standards-grounding.md)), and emits it as a `claim` event if it passes. A line that is not valid JSON or not that shape fails with reason `malformed`.
- **Limits.** At most 3 insights and 3 peer examples **emitted**. Once a section has 3 emitted claims, further lines for that section are ignored. Each claim is one or two plain sentences in the conversation language.
- **Claim identity.** Each emitted claim gets a `claim_id` (1, 2, 3 and so on within the answer). A line repeating an emitted claim (same section, source and normalized text) is dropped as a duplicate.
- **Prompt rules:**
  - cite only `source` labels and clause IDs exactly as returned by the tools;
  - use the producer's own history where relevant;
  - no directive language;
  - say nothing about what the producer should decide.
- **Fixed text.** The opening line, the limited-evidence notice and the closing hand-back are fixed text, not model output ([#13 spec](13-conversation-steps.md)).
- **Retries.** After the first pass, if a section has fewer than its limit and some lines failed, one follow-up call asks for replacements only.
  - The call receives the failed lines with their reason codes and the claims already emitted, marked "already shown, do not repeat".
  - It asks for no more claims than the open slots.
  - This repeats up to the verifier's retry limit (2 follow-up calls). Claims emitted earlier are never withdrawn or changed.
- **What is stored.** The answer saved to the conversation state, and later the record, is exactly the list of emitted claims, which is what the producer saw. If the model call fails partway, the claims already emitted are kept, and `retry_answer` moves them to earlier answers ([#13 spec](13-conversation-steps.md)).

## Testing Decisions

- **Seam 1 (agent entrypoint) with scripted model output:**
  - claims parsed line by line and emitted only after passing;
  - a malformed line treated as a failed claim;
  - limits enforced (a fourth insight ignored);
  - a duplicate line dropped;
  - a follow-up call asking only for open slots and never changing emitted claims;
  - a failure partway keeping the emitted claims as the stored answer;
  - output in the conversation language.
- **Evals (real Bedrock):**
  - every claim cited;
  - tone with no directive language;
  - distinct insights and examples for scripted producers who share a tag but differ in profile.

## Out of Scope

- Retrieval ([#14](14-producer-record-tool.md), [#15](15-regional-context-tool.md), [#16](16-peer-example-tool.md), [#17](17-standards-grounding.md))

## Further Notes

### Decisions made while writing this spec

- At most 3 insights and 3 peer examples per answer.
- Claims are written one JSON object per line, so each can be checked as soon as it is complete.
