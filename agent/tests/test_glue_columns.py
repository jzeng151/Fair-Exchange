"""Spec 28/29/37: the Glue tables Athena queries must mirror the record models.

If a record field is added (as ai_usage, evidence and closed_at were) without a Glue column, Athena can't see
it and every analytics query that reads it fails. This test reads the columns from the CDK stack and compares
them with the Python models, so the two can't drift apart.
"""
import re
from pathlib import Path

from fex.models import CompletedRecord, DeclinedRecord

STACK = Path(__file__).resolve().parents[2] / "infra" / "lib" / "athena-sync-stack.ts"
# Not exposed to Athena on purpose: the matched personal words stay in the record for reviewers only.
NOT_IN_ATHENA = {"pii_matches"}


def stack_text() -> str:
    return STACK.read_text(encoding="utf-8")


def glue_columns() -> list[str]:
    block = re.search(r"export const RECORD_COLUMNS[^=]*=\s*\[(.*?)\n\];", stack_text(), re.S)
    assert block, "RECORD_COLUMNS not found in athena-sync-stack.ts"
    return re.findall(r"name:\s*'([a-z_]+)'", block.group(1))


def test_every_record_field_has_a_glue_column():
    fields = set(CompletedRecord.model_fields) | set(DeclinedRecord.model_fields)
    missing = sorted(fields - NOT_IN_ATHENA - set(glue_columns()))
    assert not missing, f"add Glue columns for: {missing} (infra/lib/athena-sync-stack.ts RECORD_COLUMNS)"


def test_no_glue_column_without_a_record_field():
    fields = set(CompletedRecord.model_fields) | set(DeclinedRecord.model_fields)
    assert sorted(set(glue_columns()) - fields) == []


def test_personal_matches_are_not_exposed_to_athena():
    assert "pii_matches" not in glue_columns()


def test_no_duplicate_columns():
    cols = glue_columns()
    assert len(cols) == len(set(cols))


def test_the_seeded_table_is_provisioned_over_its_own_prefix():
    text = stack_text()
    assert re.search(r"SEEDED_GLUE_TABLE\s*=\s*'records_seeded'", text)
    assert re.search(r"SEEDED_PREFIX\s*=\s*'records-seeded/'", text)
    assert "${SEEDED_PREFIX}" in text and "name: SEEDED_GLUE_TABLE" in text
