"""The producer data files built by the generator (issue #7): one JSON lines file per table.

`generated/<table>/<table>.jsonl`, one folder per table so each maps to its own S3 prefix and Glue table.
"""
from __future__ import annotations

import json
from pathlib import Path

GENERATED_DIR = Path(__file__).parent / "generated"
TABLES = ("producers", "premium_projects", "survey_responses", "certifications", "peer_catalog")


def table_path(name: str, root: Path = GENERATED_DIR) -> Path:
    return root / name / f"{name}.jsonl"


def read_table(name: str, root: Path = GENERATED_DIR) -> list[dict]:
    with open(table_path(name, root), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
