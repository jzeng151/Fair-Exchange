"""Regenerate the JSON Schema and TypeScript types from the Pydantic models (issue #6).

    cd agent && uv run python scripts/generate_types.py

Writes:
  agent/schema/conversation-record.schema.json   (JSON Schema)
  api/src/types/conversation-record.ts            (TypeScript, via json-schema-to-typescript)
Needs Node.js (npx). Never edit the outputs by hand; tests/test_generated_types.py checks them.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fex.schema_export import export_json_schema  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
JSON_SCHEMA = REPO / "agent" / "schema" / "conversation-record.schema.json"
TS_TYPES = REPO / "api" / "src" / "types" / "conversation-record.ts"
JSON2TS = "json-schema-to-typescript@15.0.4"  # pinned so output is reproducible


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    schema_text = export_json_schema()
    JSON_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    JSON_SCHEMA.write_text(schema_text, encoding="utf-8")

    body = subprocess.run(
        ["npx", "--yes", "-p", JSON2TS, "json2ts", "--input", str(JSON_SCHEMA), "--bannerComment", ""],
        check=True, capture_output=True, text=True,
    ).stdout
    banner = (
        "// GENERATED FILE. Do not edit by hand.\n"
        "// Source: agent/src/fex/models.py  ->  agent/scripts/generate_types.py\n"
        f"// schema-sha256: {sha256(schema_text)}\n"
        f"// body-sha256: {sha256(body)}\n"
        "// end-of-banner\n"
    )
    TS_TYPES.parent.mkdir(parents=True, exist_ok=True)
    TS_TYPES.write_text(banner + body, encoding="utf-8")
    print(f"wrote {JSON_SCHEMA.relative_to(REPO)} and {TS_TYPES.relative_to(REPO)}")


if __name__ == "__main__":
    main()
