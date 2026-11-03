# data/

Data built from the FTUSA sample files in `docs/olena_data/`.

## APS/FPS standards (issue #9)

FEX cites a Fair Trade standard clause for every claim. This turns the two workbooks into **700 citable clauses**:

| | APS (Agricultural Production Standard) | FPS (Factory Production Standard) |
|---|---|---|
| Levels | sub-module (`APS 1.1`), objective (`APS 2.1.1`), criterion (`APS 2.1.1.a`) | same |
| Languages | English, Spanish, French (official text) | English |

Workbook quirks handled by the loader:
- APS repeats some objectives once per farm size (SF/MF/LF). These are merged into one clause with `farm_sizes`.
- Amendment variants (`_vCNVN`, `_vEUDR`, `_vUS`, …) are kept under their base clause in `variants`; they are never separate citations.
- APS has no sub-module rows, so headings are built from its `Sub-Module` column.

### Use it

```python
from fx_data.standards import Standards

standards = Standards.load()
standards.get("APS 2.1.1")            # the clause dict, or None
standards.exists("APS 2.1.1")         # True/False, for the citation verifier (#17)
standards.search("trabajo forzoso")   # by text, English/Spanish/French, best first
```

### Rebuild `standards/clauses.json`

The JSON is committed, so nothing parses Excel at runtime. After the workbooks change:

```bash
cd data && uv sync
PYTHONPATH=src uv run python -m fx_data.standards_loader
```

`tests/test_standards_lookup.py` fails if `clauses.json` no longer matches the workbooks.

### Tests

```bash
cd data && uv sync && uv run pytest
```
