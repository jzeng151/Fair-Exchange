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

### Rebuild `src/fx_data/clauses.json`

The JSON is committed and ships inside the `fx_data` package, so nothing parses Excel at runtime. After the workbooks change:

```bash
cd data && uv sync
PYTHONPATH=src uv run python -m fx_data.standards_loader
```

`tests/test_standards_lookup.py` fails if `clauses.json` no longer matches the workbooks.

### Tests

```bash
cd data && uv sync && uv run pytest
```

## Regional fact table (issue #8)

"What the data shows" for a producer's region and crop, pre-extracted so nothing calls an outside service at runtime.

| Source | What | Per |
|---|---|---|
| CHIRPS v2.0 (via SERVIR ClimateSERV) | Rainfall in 2024-2025 vs the 2014-2023 average | region |
| WRI Aqueduct 4.0 | Baseline water stress, and projected stress for 2030 and 2050 (business as usual) | region (river basin at the point) |
| World Bank Pink Sheet | Benchmark price change over 12 months and vs the 5-year average: Arabica coffee, cocoa, US bananas | crop |

56 regions in 16 countries, including all of Peru, Côte d'Ivoire, Colombia, Honduras and Mexico in the sample. Each region is one point near its centre (`REGIONS` in `regional.py`), so climate and water facts have strength `nearest`. Prices are world benchmarks, not farm-gate prices, so they have strength `limited`.

```python
from fx_data.regional import RegionalFacts
facts = RegionalFacts.load()
answer = facts.lookup("Colombia", "Cauca", "Coffee")
answer.facts   # [{"text", "source", "metric", "value", "unit", "period", "strength"}, ...]
```

`lookup` never substitutes another region: an unknown region returns crop prices only (`match_level="country"`), or nothing.

### Rebuild

```bash
PYTHONPATH=src uv run python -m fx_data.regional fetch   # network, ~15 min -> regional_sources.json
PYTHONPATH=src uv run python -m fx_data.regional build   # offline -> regional_facts.json
```

Both files are committed. `tests/test_regional.py` fails if `regional_facts.json` no longer matches `regional_sources.json`. To add a region, add it to `REGIONS` and run both steps. The Pink Sheet workbook URL changes each year; update `PINK_SHEET_URL` when it does.

## Peer projects and producer profiles (issue #16)

```bash
PYTHONPATH=src uv run python -m fx_data.peers   # offline -> peer_projects.json, producer_profiles.json
```

- **`peer_projects.json`**: 347 of the 349 environmental Premium projects (2 lorem-ipsum placeholder rows dropped), each with a challenge tag, status and dates. Organizations get a stable `ORG-xxxxxxxx` reference, and organization and person names in the text are replaced (`NAME_REPLACEMENTS` in `peers.py`). The owning account is stored only as a salted hash (`owner_key`) so a producer's own projects can be left out.
- **`producer_profiles.json`**: producer id → country, region, crop, entity type. A stand-in until the producer-record tool (#14) and the Athena tables (#28) exist. Region is the region most of the producer's projects are in; 7 of the 146 sample producers have none.

`tests/test_peers.py` fails if either file is stale, or if an account id or a listed name appears in `peer_projects.json`.
