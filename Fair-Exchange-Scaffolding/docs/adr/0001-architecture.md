# ADR 0001: Fair Exchange architecture

**Status:** proposed

## Decision
- **Agent:** Strands (Python 3.12) on Amazon Bedrock AgentCore Runtime. All model access through Amazon Bedrock, using `us.` inference profiles.
- **Models:** the smallest model that does each job well. Start with Claude Haiku for questions, playback and tagging, and Claude Sonnet for the grounded answer; let `eval/` decide. (A one-question spike found Haiku met every rule, at about 7x lower estimated energy.)
- **Scope:** tools read `producer_id` from `invocation_state`, set by the API from the login. Never a model-settable parameter.
- **Schemas:** Pydantic in `agent/` is the single source; JSON Schema and TS types are generated.
- **Storage:** DynamoDB for records, S3 + Glue/Athena as the Redshift stand-in, Knowledge Bases on S3 Vectors.
- **Infra:** one CDK (TypeScript) stack.

## Consequences
- Switching models is a config change (`FEX_MODEL_SMALL` / `FEX_MODEL_LARGE`).
- AI usage (tokens per call, model size) is logged per conversation, for the AI footprint on the dashboard.
