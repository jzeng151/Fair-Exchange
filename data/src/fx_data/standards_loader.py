"""Build citable APS/FPS clause records from the FTUSA workbooks (issue #9).

    cd data && uv run python -m fx_data.standards_loader

Reads docs/olena_data/*.xlsm and writes data/src/fx_data/clauses.json (committed and shipped
with the package, so nothing
parses Excel at runtime). Clause IDs look like "APS 2.1.1" (objective), "APS 2.1.1.a" (criterion)
and "FPS 1.1" (sub-module heading). They match the `standard_clause` citation format.

Workbook quirks handled here:
- APS repeats some objectives once per farm size (SF/MF/LF): merged into one clause with `farm_sizes`.
- Amendment variants (e.g. "1.1.1.a_vCNVN", "_vEUDR") are attached to their base clause as
  `variants`, never separate citations.
- APS has official Spanish and French text; FPS (Factory Production Standard) is English only.
"""
import json
import re
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[3]
OLENA = REPO / "docs" / "olena_data"
OUTPUT = REPO / "data" / "src" / "fx_data" / "clauses.json"  # inside the package, so it ships with it

# (standard, workbook, objectives sheet, criteria sheet, languages with official text)
SOURCES = [
    ("APS", "APS 10.22.26.xlsm", "Set English", "Questions English", ("en", "es", "fr")),
    ("FPS", "FPS for import 7.8.26.xlsm", "Set English FPS", "Questions English FPS", ("en",)),
]
FARM_SIZE_ORDER = ["SF", "MF", "LF"]
_SUFFIX = {"en": "", "es": "_ES", "fr": "_FR"}


def _rows(workbook: Path, sheet: str) -> list[dict]:
    """Rows of a sheet as dicts, using the first non-empty row as the header."""
    ws = openpyxl.load_workbook(workbook, read_only=True, data_only=True)[sheet]
    rows = ws.iter_rows(values_only=True)
    header = next(r for r in rows if any(c not in (None, "") for c in r))
    keys = [str(h).strip() if h is not None else "" for h in header]
    return [dict(zip(keys, r)) for r in rows if any(c not in (None, "") for c in r)]


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip() if value not in (None, "") else ""


def _split_variant(raw: str) -> tuple[str, str | None]:
    """'1.1.1.a_vCNVN' -> ('1.1.1.a', 'vCNVN')."""
    base, _, variant = raw.partition("_")
    return base, (variant or None)


def _level(number: str) -> str:
    parts = number.split(".")
    if parts[-1].isalpha():
        return "criterion"
    return {2: "sub-module", 3: "objective"}.get(len(parts), "other")


def _parent(standard: str, number: str) -> str | None:
    parts = number.split(".")
    return f"{standard} {'.'.join(parts[:-1])}" if len(parts) > 2 else None


def _sort_key(clause: dict):
    return (clause["standard"], [int(p) if p.isdigit() else p for p in clause["number"].split(".")])


def _upsert(clauses: dict, standard: str, raw_number, text: dict, *, farm_size=None,
            module="", sub_module="", intent=""):
    raw = _clean(raw_number)
    if not raw:
        return
    number, variant = _split_variant(raw)
    cid = f"{standard} {number}"
    clause = clauses.get(cid)
    if clause is None:
        clause = clauses[cid] = {
            "id": cid, "standard": standard, "number": number, "level": _level(number),
            "parent": _parent(standard, number), "module": module, "sub_module": sub_module,
            "farm_sizes": [], "variants": [], "text": {}, "intent": intent,
        }
    if variant:
        if variant not in clause["variants"]:
            clause["variants"].append(variant)
    else:
        # the base row's wording wins over any variant wording
        clause["text"].update({k: v for k, v in text.items() if v})
        clause["intent"] = clause["intent"] or intent
    for lang, value in text.items():  # a clause known only through a variant still gets text
        if value and lang not in clause["text"]:
            clause["text"][lang] = value
    if farm_size and farm_size not in clause["farm_sizes"]:
        clause["farm_sizes"].append(farm_size)
        clause["farm_sizes"].sort(key=FARM_SIZE_ORDER.index)


def _ensure_heading(clauses: dict, standard: str, row: dict, languages, module: str):
    """APS has no sub-module rows, only a 'Sub-Module' column ("Sub-Module 1.1: ..."). Create the
    heading clause from it so objectives' parents exist. Never overwrite a real heading row."""
    match = re.search(r"(\d+\.\d+)\b", _clean(row.get("Sub-Module")))
    if not match:
        return
    cid = f"{standard} {match.group(1)}"
    texts = {lang: _clean(row.get("Sub-Module" + _SUFFIX[lang])) for lang in languages}
    if cid not in clauses:
        _upsert(clauses, standard, match.group(1), texts, module=module)
    else:
        for lang, value in texts.items():
            if value and lang not in clauses[cid]["text"]:
                clauses[cid]["text"][lang] = value


def build_clauses(olena: Path = OLENA) -> list[dict]:
    clauses: dict[str, dict] = {}
    for standard, workbook, objectives_sheet, criteria_sheet, languages in SOURCES:
        path = olena / workbook
        for row in _rows(path, objectives_sheet):
            _ensure_heading(clauses, standard, row, languages, _clean(row.get("Tab")))
            _upsert(clauses, standard, row.get("Number"),
                    {lang: _clean(row.get("Name" + _SUFFIX[lang])) for lang in languages},
                    farm_size=_clean(row.get("Farm size")) or None,
                    module=_clean(row.get("Tab")), sub_module=_clean(row.get("Sub-Module")))
        for row in _rows(path, criteria_sheet):
            _upsert(clauses, standard, row.get("Code"),
                    {lang: _clean(row.get("Question" + _SUFFIX[lang])) for lang in languages},
                    intent=_clean(row.get("Intent")))
    return sorted(clauses.values(), key=_sort_key)


def export_text(olena: Path = OLENA) -> str:
    """clauses.json content: stable, sorted text."""
    return json.dumps(build_clauses(olena), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(export_text(), encoding="utf-8")
    count = OUTPUT.read_text(encoding="utf-8").count('"id":')
    print(f"wrote {OUTPUT.relative_to(REPO)} ({count} clauses)")


if __name__ == "__main__":
    main()
