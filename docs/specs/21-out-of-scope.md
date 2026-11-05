# Spec: Out-of-scope handling (#21)

Status: approved for build, 2026-11-04. Detection method approved by the repo owner, 2026-11-05.

## Problem Statement

Producers will ask FEX for things it is not built for, such as their certification status or a worker voice complaint. An improvised answer is wrong at best and harmful at worst. A misdirected request also must not end up in the record as if it were the producer's challenge.

## Solution

FEX declines the request, says plainly why, and offers to return to the open question about what has been difficult. One detection function uses the configured small Bedrock model to classify the message. The record is built only from the confirmed playback, so nothing from the misdirected request reaches it.

## User Stories

1. As a producer who asks something FEX does not do, I want FEX to say plainly that it cannot help with that and why, so that I am not given an improvised answer.
2. As a producer, I want to be able to go back to describing my challenge afterwards, so that the conversation is not wasted.
3. As a producer, I want to be able to end the conversation if I have nothing else to discuss, so that I am not pushed into describing a challenge.
4. As a producer, I want to still see anonymized examples of what other producers tried, so that declining protected requests does not remove peer examples.
5. As an FTUSA reviewer, I want nothing from a misdirected request in the record, so that records reflect producers' challenges only.

## Implementation Decisions

- **Detection function.** One function takes the producer's message and current step. The live runtime uses the configured small Bedrock model with the detect-mode Guardrail, no data tools, and a validated structured result: one of `in_scope`, `certification_status`, `grievance`, `other_producer_data`, plus `en`, `es` or `fr`. It never generates the refusal wording. The producer message is untrusted classification input, not instructions. The offline demo retains its no-AWS stand-in.
- **Failure.** If classification fails or produces an invalid result, no answering model or data tool receives that message. FEX keeps the current step, shows a fixed retry message in the conversation's language, and excludes the failed exchange from future model prompts, playback and PII scanning. Retention and visible resume history follow the existing memory policy.
- **Boundaries.** General standards guidance, ordinary labor challenges, certification mentioned as background and anonymized peer examples are in scope. Mixed messages containing a prohibited request are declined as a whole; the producer can send their farming challenge separately.
- **Out-of-scope requests** include:
  - certification status or audit results;
  - worker voice or grievance complaints;
  - requests for another named producer's own records, conversations or data.
- **In-scope requests** include anonymized peer examples returned by the peer-example tool. They remain part of every answer.
- **Response.** FEX declines with a one-sentence reason in the producer's language and offers to return to the open question. It does not call any data tool for the request.
- **Steps.** The conversation stays in its current step. If the producer has nothing else, they use `end` ([#13 spec](13-conversation-steps.md)).
- **Record.** Summaries and tags are generated from the confirmed playback only ([#26 spec](26-write-back.md)). The playback must not include the misdirected request. PII results from out-of-scope messages are not recorded either ([#20 spec](20-pii-flagging.md)).

## Testing Decisions

Seam 1 (agent entrypoint) with a fake detection function and scripted model output, per the [specs README](README.md). Cases:
- an out-of-scope request triggering no data tool call;
- the step unchanged;
- a later confirmed playback and record containing none of the misdirected text;
- a request for peer examples treated as in scope.

The classifier adapter is tested with scripted Strands output, including invalid responses and provider failures. A synthetic live-Bedrock check covers the three refusal categories, English/Spanish/French, injection attempts, mixed requests, and permitted peer/labor/standards questions. This finite set is evidence, not a guarantee of perfect classification.

## Out of Scope

- Routing producers to the right FTUSA channel for the request

## Further Notes

### Not decided (do not build or assume)

- What outcome and record a conversation gets when the producer leaves after only an out-of-scope request ([#13 spec](13-conversation-steps.md))
