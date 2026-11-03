"""Issue #6: JSON Schema and TypeScript types are GENERATED from the Pydantic models.
These tests fail if the models change without regenerating, or if a generated file is hand-edited.
Regenerate with:  uv run python scripts/generate_types.py
"""
import hashlib
import re
from pathlib import Path

from fex.schema_export import export_json_schema

REPO = Path(__file__).resolve().parents[2]
JSON_SCHEMA = REPO / "agent" / "schema" / "conversation-record.schema.json"
TS_TYPES = REPO / "api" / "src" / "types" / "conversation-record.ts"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def banner_value(ts: str, key: str) -> str:
    match = re.search(rf"^// {key}: ([0-9a-f]{{64}})$", ts, re.M)
    assert match, f"TypeScript file is missing its '{key}' banner line; regenerate it"
    return match.group(1)


def test_json_schema_file_matches_the_models():
    assert JSON_SCHEMA.read_text(encoding="utf-8") == export_json_schema(), \
        "agent/schema JSON is stale; run scripts/generate_types.py"


def test_typescript_types_come_from_the_current_schema():
    ts = TS_TYPES.read_text(encoding="utf-8")
    assert banner_value(ts, "schema-sha256") == sha256(export_json_schema()), \
        "TypeScript types are stale; run scripts/generate_types.py"


def test_typescript_types_were_not_hand_edited():
    ts = TS_TYPES.read_text(encoding="utf-8")
    body = ts.split("// end-of-banner\n", 1)[1]
    assert banner_value(ts, "body-sha256") == sha256(body), \
        "TypeScript types were edited by hand; change the Pydantic models and regenerate instead"
