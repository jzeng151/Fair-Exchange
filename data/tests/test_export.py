"""The data bucket export (#5, #7, #14): the package's producer data as JSON-lines tables for S3 and Athena.

The files are what Athena's Glue tables read, so their fields must match the CDK columns exactly
(infra/lib/data-bucket.ts SOURCE_TABLES). Only already-allowlisted data is exported: profiles, Premium projects,
survey summary facts (never raw survey answers), certification scope and the fictional peer catalog.
"""
import json
import re
from pathlib import Path

import pytest

from fx_data.export import TABLES, export_tables

ROOT = Path(__file__).resolve().parents[2]
DATA_BUCKET_TS = ROOT / "infra" / "lib" / "data-bucket.ts"
RECORDS = json.loads((ROOT / "data" / "src" / "fx_data" / "producer_records.json").read_text(encoding="utf-8"))["records"]


def rows(out: Path, table: str) -> list[dict]:
    return [json.loads(line) for line in (out / table / f"{table}.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("export")
    export_tables(path)
    return path


def test_writes_one_jsonl_file_per_table_under_its_own_prefix(out):
    assert sorted(p.name for p in out.iterdir()) == sorted(TABLES)
    for table in TABLES:
        assert [p.name for p in (out / table).iterdir()] == [f"{table}.jsonl"]


def test_counts_match_the_package_data(out):
    assert len(rows(out, "producers")) == len(RECORDS)
    assert len(rows(out, "certification")) == len(RECORDS)
    assert len(rows(out, "premium_projects")) == sum(len(r["premium_projects"]) for r in RECORDS.values())
    assert len(rows(out, "survey_facts")) == sum(len(r["survey"]["facts"]) for r in RECORDS.values())


def test_every_row_has_the_producer_id_and_exactly_the_table_fields(out):
    for table, fields in TABLES.items():
        for row in rows(out, table):
            assert list(row) == list(fields), table
        if table != "peer_catalog":
            assert all(row["producer_id"] in RECORDS for row in rows(out, table)), table


def test_is_deterministic(out, tmp_path):
    export_tables(tmp_path)
    for table in TABLES:
        assert (tmp_path / table / f"{table}.jsonl").read_bytes() == (out / table / f"{table}.jsonl").read_bytes()


def test_never_exports_raw_survey_answers(out):
    # Survey data leaves only as allowlisted summary facts with at least the package's minimum responses
    from fx_data.records import MIN_RESPONSES
    facts = rows(out, "survey_facts")
    assert facts and all(f["responses"] >= MIN_RESPONSES for f in facts)
    raw_markers = {"survey_response_sk", "household_sk", "respondent", "answer"}
    for table in TABLES:
        for row in rows(out, table):
            assert not raw_markers & set(row), table


def test_glue_columns_in_cdk_match_the_exported_fields():
    text = DATA_BUCKET_TS.read_text(encoding="utf-8")
    block = re.search(r"export const SOURCE_TABLES[^=]*=\s*\{(.*?)\n\};", text, re.S)
    assert block, "SOURCE_TABLES not found in infra/lib/data-bucket.ts"
    glue = {name: re.findall(r"name:\s*'([a-z_]+)'", cols)
            for name, cols in re.findall(r"\n  ([a-z_]+):\s*\[(.*?)\n  \]", block.group(1), re.S)}
    athena_tables = {t: f for t, f in TABLES.items() if t != "peer_catalog"}  # the peer catalog is for the tool only
    assert glue == {t: list(f) for t, f in athena_tables.items()}
