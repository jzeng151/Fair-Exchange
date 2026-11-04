"""Issue #13: the request/action/event contract is generated for TypeScript, like the record schema.
Fails if the Pydantic contract changes without regenerating, or if a generated file is hand-edited.
Regenerate with:  uv run python scripts/generate_types.py
"""
import json

from tests.test_generated_types import REPO, banner_value, sha256

from fex.schema_export import export_contract_schema

JSON_SCHEMA = REPO / "agent" / "schema" / "conversation-contract.schema.json"
TS_TYPES = REPO / "api" / "src" / "types" / "conversation-contract.ts"


def test_contract_json_schema_matches_the_models():
    assert JSON_SCHEMA.read_text(encoding="utf-8") == export_contract_schema(), \
        "contract JSON Schema is stale; run scripts/generate_types.py"


def test_contract_typescript_comes_from_the_current_schema():
    ts = TS_TYPES.read_text(encoding="utf-8")
    assert banner_value(ts, "schema-sha256") == sha256(export_contract_schema())


def test_contract_typescript_was_not_hand_edited():
    ts = TS_TYPES.read_text(encoding="utf-8")
    assert banner_value(ts, "body-sha256") == sha256(ts.split("// end-of-banner\n", 1)[1])


def test_contract_covers_every_request_kind_action_and_event_type():
    text = export_contract_schema()
    for name in ["start", "message", "action", "resume", "auto_close",
                 "confirm_playback", "correct_playback", "reopen_playback", "retry_answer", "set_consent",
                 "set_feedback", "end",
                 "text", "claim", "answer", "step", "actions", "record_saved", "error", "done"]:
        assert f'"{name}"' in text, name
    schema = json.loads(text)
    assert "producerId" in json.dumps(schema)  # the wire names the chat API sends
