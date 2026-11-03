# agent/

FEX, Fair Exchange's agent (Python 3.12). For now this holds the **conversation record schema** (issue #6).

## Record schema

`src/fex/models.py` is the **single source of truth**. Two record types, chosen by `status`:

| | `CompletedRecord` | `DeclinedRecord` |
|---|---|---|
| When | The producer agreed to save | The producer declined |
| Consent scope | `internal` or `internal_and_outward` | `declined` |
| Content | Producer's words (+ English for non-English), 11-tag challenge tags, the insights and peer examples given (each with a required citation: source + APS/FPS clause + evidence strength), feedback, PII flag, review status | Identifiers, status and time only. Any narrative field is rejected |
| `source` | always `"agent conversation"` | always `"agent conversation"` |

Use `parse_record(data)` to validate stored or incoming data; it picks the type from `status`.

## Generated files (never edit by hand)

- `schema/conversation-record.schema.json`: JSON Schema
- `../api/src/types/conversation-record.ts`: TypeScript types

After changing `models.py`, regenerate (needs Node.js):

```bash
uv run python scripts/generate_types.py
```

`tests/test_generated_types.py` fails if the models change without regenerating, or if a generated file is edited by hand.

## Tests

```bash
uv sync
uv run pytest
```
