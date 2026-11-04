# Spec: Bedrock Guardrail in detect mode (#12)

Status: approved for build, 2026-11-04.

## Problem Statement

The technical environment requires Bedrock Guardrails on every agent model call as the responsible-AI layer, configured to flag rather than block, so the review flow is exercised. Without a defined configuration and a place to record what it detects, the Guardrail either blocks the conversation or produces findings nobody sees.

## Solution

One Guardrail, defined in CDK, attached to every Bedrock model call FEX makes, with every policy in detect mode. Its assessments go to CloudWatch, so engineers can see them. They change no behavior in the MVP and are not written to the record.

## User Stories

1. As an FTUSA engineer, I want Guardrail findings logged with the conversation ID, so that I can audit when conversations touched sensitive topics.
2. As a producer, I want the Guardrail never to block or alter my conversation, so that my words reach FEX as I wrote them.
3. As an FTUSA engineer, I want the Guardrail defined in CDK and attached to every model call, so that governance is consistent and deploys in one command.

## Implementation Decisions

- **Configuration (CDK):**
  - **Denied topics:** certification status and audit results; worker grievances and complaints.
  - **Content filters:** standard categories.
  - **Actions:** every policy action is `NONE` (detect) for both input and output.
  - **Sensitive information filter ([#24](24-french-exchange.md)):** `NAME`, `PHONE`, `EMAIL`, `ADDRESS`, action `NONE` (detect only) for input and output. On ordinary model calls its findings go to CloudWatch like any other. The French PII path ([#20 spec](20-pii-flagging.md)) calls the Guardrail directly on the producer's text to fill the record's PII fields, since Comprehend has no French.
  - **Not configured:** the contextual grounding check (the citation verifier covers grounding).
- **Attachment.** Every Bedrock model call goes through the Strands Bedrock model with the Guardrail ID and version and trace enabled. The IDs are configuration values. Input and output redaction are set to off explicitly (`guardrail_redact_input` and `guardrail_redact_output` false), so nothing is altered even if a policy action is changed later.
- **Recording.** Each assessment with a detected policy is logged to CloudWatch with the conversation ID, policy type and topic or category only, never text. It is not written to the record, because #21 keeps anything derived from a misdirected request out of the record.
- **Behavior.** No effect on steps, answers or records in the MVP. Whether the Guardrail feeds out-of-scope detection is part of the undecided detection function ([#21 spec](21-out-of-scope.md)).

## Testing Decisions

- **Seam 1 (agent entrypoint)** with a model stub returning a Guardrail trace: the finding is logged without text, nothing is added to the record, and the conversation continues unchanged.
- **Seam 3 (deployed smoke test):** within a scripted conversation that continues through consent, a message asking for certification status produces a denied-topic finding in CloudWatch.

## Out of Scope

- Blocking or masking anything
- (French PII is now in scope via the sensitive-information filter above, [#24](24-french-exchange.md))

## Further Notes

### Spike checks (#4)

- Detect-mode assessments are returned in the trace when every action is `NONE`
