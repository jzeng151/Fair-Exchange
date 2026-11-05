"""Export the producer data as JSON-lines tables for the data bucket (#5, #7, #14).

    uv run python -m fx_data.export <out_dir>     # infra/deploy.sh uploads <out_dir> to the data bucket

One folder per table, one `<table>.jsonl` file in it, so each Glue table (infra/lib/data-bucket.ts) points at
its own S3 prefix. Only data that is already allowlisted leaves the package: profiles, Premium projects,
survey summary facts (never raw survey answers), certification scope and the fictional peer catalog.

The input is the generator's tables (fx_data.generator, #7), so the bucket, Athena and the agent's tools
read the same fields. Survey responses are the one table not exported as is: they leave only as the
summary facts the producer-record tool builds from them (fx_data.records).
The output is deterministic: rows sorted by their IDs, keys in a fixed order, no timestamps.
"""
import json
import sys
from pathlib import Path

from fx_data.records import build_records
from fx_data.tables import read_table

# table -> fields, in order. The Glue columns in infra/lib/data-bucket.ts must match (data/tests/test_export.py).
TABLES: dict[str, tuple[str, ...]] = {
    "producers": ("producer_id", "country", "admin1", "crops", "entity_type", "origin"),
    "certification": ("producer_id", "certification_scope"),
    "premium_projects": ("project_id", "producer_id", "title", "category", "sub_category", "tags", "start_year",
                         "amount", "description"),
    "survey_facts": ("producer_id", "survey_column", "text", "source", "period", "responses"),
    # For the peer tool only (no Glue table): owner_producer_id is private and never returned (#16)
    "peer_catalog": ("catalog_id", "owner_producer_id", "tags", "country", "crop", "entity_type", "category",
                     "sub_category", "start_year", "description", "organization"),
}


def _pick(row: dict, fields: tuple[str, ...], **extra) -> dict:
    merged = {**row, **extra}
    return {f: merged.get(f) for f in fields}


def build_tables() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {t: [] for t in TABLES}
    for p in sorted(read_table("producers"), key=lambda p: p["producer_id"]):
        out["producers"].append(_pick(p, TABLES["producers"]))
    for c in sorted(read_table("certifications"), key=lambda c: c["producer_id"]):
        out["certification"].append(_pick(c, TABLES["certification"]))
    for p in sorted(read_table("premium_projects"), key=lambda p: p["project_id"]):
        out["premium_projects"].append(_pick(p, TABLES["premium_projects"]))
    records = build_records()
    for pid in sorted(records):
        for f in sorted(records[pid]["survey"]["facts"], key=lambda f: f["column"]):
            # `column` is reserved in Athena DDL, so the table calls it survey_column
            out["survey_facts"].append(_pick(f, TABLES["survey_facts"], producer_id=pid, survey_column=f["column"]))
    for p in sorted(read_table("peer_catalog"), key=lambda p: p["catalog_id"]):
        out["peer_catalog"].append(_pick(p, TABLES["peer_catalog"]))
    return out


def export_tables(out_dir: Path) -> dict[str, int]:
    """Write every table; returns the row count per table."""
    counts = {}
    for table, table_rows in build_tables().items():
        folder = Path(out_dir) / table
        folder.mkdir(parents=True, exist_ok=True)
        lines = (json.dumps(row, ensure_ascii=False, sort_keys=False) for row in table_rows)
        (folder / f"{table}.jsonl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        counts[table] = len(table_rows)
    return counts


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m fx_data.export <out_dir>")
    for name, count in export_tables(Path(sys.argv[1])).items():
        print(f"{name}: {count} rows")
