"""Regenerate the JSON Schema and TypeScript types from the Pydantic models (issue #6).

    cd agent && uv run python scripts/generate_types.py

Writes:
  agent/schema/conversation-record.schema.json     + api/src/types/conversation-record.ts     (record, #6)
  agent/schema/conversation-contract.schema.json   + api/src/types/conversation-contract.ts   (API contract, #13)
Needs Node.js (npx). Never edit the outputs by hand; tests/test_generated_types.py checks them.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fex.schema_export import export_contract_schema, export_json_schema  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
JSON2TS = "json-schema-to-typescript@15.0.4"  # pinned so output is reproducible
OUTPUTS = [  # (export function, JSON Schema path, TypeScript path, Python source)
    (export_json_schema, REPO / "agent" / "schema" / "conversation-record.schema.json",
     REPO / "api" / "src" / "types" / "conversation-record.ts", "agent/src/fex/models.py"),
    (export_contract_schema, REPO / "agent" / "schema" / "conversation-contract.schema.json",
     REPO / "api" / "src" / "types" / "conversation-contract.ts", "agent/src/fex/conversation/contract.py"),
]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    for export, json_path, ts_path, source in OUTPUTS:
        schema_text = export()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(schema_text, encoding="utf-8")
        body = subprocess.run(
            ["npx", "--yes", "-p", JSON2TS, "json2ts", "--input", str(json_path), "--bannerComment", ""],
            check=True, capture_output=True, text=True,
        ).stdout
        banner = (
            "// GENERATED FILE. Do not edit by hand.\n"
            f"// Source: {source}  ->  agent/scripts/generate_types.py\n"
            f"// schema-sha256: {sha256(schema_text)}\n"
            f"// body-sha256: {sha256(body)}\n"
            "// end-of-banner\n"
        )
        ts_path.parent.mkdir(parents=True, exist_ok=True)
        ts_path.write_text(banner + body, encoding="utf-8")
        print(f"wrote {json_path.relative_to(REPO)} and {ts_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
