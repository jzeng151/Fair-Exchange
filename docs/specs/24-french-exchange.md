# Spec: French exchange (#24)

Status: approved for build, 2026-11-04. Nice-to-have: start only after every must-have is done.

## Problem Statement

Côte d'Ivoire is a 2027 workshop country, and its producers work in French. The MVP proves the multilingual pattern in Spanish. French is the next step, but it has one gap Spanish doesn't: Amazon Comprehend's PII detection doesn't support French. Without a plan, a French conversation's PII check is "unsupported", and every French record is flagged for review.

## Solution

FEX handles a full exchange in French using the same language rules as Spanish ([#22](22-spanish-exchange.md)). The record is stored in French and English. PII in French text is detected through the FEX Guardrail's sensitive-information filter in detect mode, called directly on the producer's text. It fills the same PII fields Comprehend fills for English and Spanish.

## User Stories

1. As a French-speaking producer in Côte d'Ivoire, I want the whole conversation, including buttons, in French, so that I can use it without translation.
2. As an FTUSA reviewer, I want the French summary and an English version on the record, so that I can review French conversations.
3. As an FTUSA reviewer, I want names and contact details in French text flagged like they are in English and Spanish, so that French records get the same PII review.
4. As a French-speaking producer, I want my "your record" view in French, so that I can read what was stored.

## Implementation Decisions

### What this spec adds

- **Language code** `fr` joins `en` and `es` in the [#22](22-spanish-exchange.md) rules. The opening question uses the profile language, then switches once identified. Summaries are kept in French plus English, and tags use the English values.
- **Fixed text and labels:**
  - the answer's fixed opening line, limited-evidence notice and hand-back exist in French ([#13](13-conversation-steps.md));
  - UI copy and tag names in the web app's copy file gain French ([#32](32-your-record.md)).
- **Standards.** No change. Knowledge Base queries use the English summary ([#17](17-standards-grounding.md)). Claims cite clause IDs, which don't depend on language.

### French PII through the Guardrail

- **Guardrail change ([#12](12-guardrail.md)).** The FEX Guardrail adds a sensitive-information filter for `NAME`, `PHONE`, `EMAIL` and `ADDRESS`, with action `NONE` (detect only) for input and output. On ordinary model calls, its findings go to CloudWatch only, like every other Guardrail finding.
- **PII change ([#20](20-pii-flagging.md)).** For `fr` conversations, each producer text is checked with the Guardrail's apply-guardrail operation (input source) instead of Comprehend. The returned PII detections fill `pii_flag`, `pii_entity_types` and `pii_matches` (match plus about 10 words either side). The same per-text status, failure and out-of-scope rules apply. `unsupported_language` remains for languages other than `en`, `es` and `fr`.
- **No confidence threshold for French.** Guardrail detections carry no confidence score, so every detected `NAME`, `PHONE`, `EMAIL` or `ADDRESS` counts. The 0.8 threshold applies to Comprehend only.
- **Permissions.** No change: the agent role already has `bedrock:ApplyGuardrail` ([#13](13-conversation-steps.md)).

### Changes to other specs, made in the PR that builds this

These contracts are owned elsewhere, so the build PR edits those specs. Nothing changes before #24 is built.
- **[#17](17-standards-grounding.md):** the shared directive-phrase list gains French phrases, e.g. "vous devriez", "nous recommandons", "la meilleure option", "il faut que vous".
- **[#20](20-pii-flagging.md):**
  - the language rule adds `fr` through the Guardrail;
  - the threshold applies to Comprehend only;
  - the test "a French conversation flags with `unsupported_language`" changes to cover a language other than `en`, `es` and `fr`.
- **[#22](22-spanish-exchange.md):** the language rules list `fr`.
- **[#12](12-guardrail.md):** the sensitive-information filter above is added to the configuration.

### Scenario

A French scenario S8 is added to the scenario files ([#35](35-scenarios-and-labels.md)): a Côte d'Ivoire cocoa producer in French who mentions a person by name and consents with `internal`. It runs in the eval ([#36](36-eval-harness.md)).

## Testing Decisions

- **Seam 1 (agent entrypoint)** with scripted French model output and a stubbed Guardrail response:
  - `language` is `fr`;
  - the French and English summaries are present;
  - a name detected by the Guardrail fills the PII fields with match and context;
  - a Guardrail error sets `failed`;
  - a directive phrase in French fails the claim check;
  - the fixed text is in French.
- **Component tests:** French labels in the chat and "your record" views.
- **Eval:** S8 meets its expected outcomes.

## Out of Scope

- Other languages
- Translating clause text into French for display (claims show clause IDs)

## Further Notes

### Spike check

- The Guardrail's sensitive-information filter detects `NAME`, `PHONE`, `EMAIL` and `ADDRESS` in French text and returns the matched text in detect mode
