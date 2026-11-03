# agent/

FEX, the Strands agent, hosted on Amazon Bedrock AgentCore Runtime.

| File | Purpose |
|---|---|
| `src/fex/app.py` | AgentCore entrypoint. Takes the request, sets `producer_id` in `invocation_state` from the API (never from the producer's text) |
| `src/fex/agent.py` | Builds the Strands `Agent`: model, system prompt, tools, Guardrail |
| `src/fex/config.py` | Model IDs (small vs. large), region, Guardrail ID |
| `src/fex/prompts.py` | FEX system prompt: plain language, cite sources, never directive, hand the decision back |
| `src/fex/models.py` | **Pydantic schemas, the single source of truth** (JSON Schema and TS types are generated from these) |
| `src/fex/tools/` | One file per tool. Each reads `producer_id` from `tool_context.invocation_state` |
| `tests/` | Unit tests, including the scope guard test |

```bash
uv sync
uv run pytest
```
