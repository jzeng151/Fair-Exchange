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

56 regions in 16 countries, including all of Peru, Côte d'Ivoire, Colombia, Honduras and Mexico in the sample. Each region is one point near its centre (`REGIONS` in `regional.py`).

The table is `src/fx_data/regional_facts.csv`, one fact per row, with exactly the #8 spec columns: `fact_id, scope, country, admin1, crop, tags, indicator, value, unit, comparison, period, source_name, source_url, extracted_at, curated`. `RegionalFacts.load()` validates every row and fails on a bad one.

- `scope` is `region` (one point near the region's centre), `country` (the average of that country's region rows in this table, said in `comparison`) or `global` (benchmark prices, by `crop`).
- `fact_id` is `RF-` plus a hash of scope, country, admin1, crop and indicator, so it stays the same across rebuilds.
- `tags` are the challenge tags the indicator speaks to (`INDICATOR_TAGS` in `regional.py`), `;`-separated.
- Prices are world benchmarks, not farm-gate prices; their `comparison` says so.

```python
from fx_data.regional import RegionalFacts
facts = RegionalFacts.load()
items = facts.lookup("Colombia", "Cauca", {"coffee"}, {"water", "climate and weather"})
# [{"source", "kind": "regional", "text", "period", "strength", "data": <the CSV row>}, ...]
```

`lookup` (#15) returns region rows (`exact`), then country rows (`nearest`), then global rows (`limited`), at most 8, filtered by tag and crop. It never substitutes another region; nothing matching is an empty list.

### Rebuild

```bash
PYTHONPATH=src uv run python -m fx_data.regional fetch   # network, ~15 min -> regional_sources.json
PYTHONPATH=src uv run python -m fx_data.regional build   # offline -> regional_facts.csv
```

Both files are committed. `tests/test_regional.py` fails if `regional_facts.csv` no longer matches `regional_sources.json`. To add a region, add it to `REGIONS` and run both steps. The Pink Sheet workbook URL changes each year; update `PINK_SHEET_URL` when it does.

## Peer projects and producer profiles (issue #16)

```bash
PYTHONPATH=src uv run python -m fx_data.peers   # offline -> peer_projects.json, producer_profiles.json
```

- **`peer_projects.json`**: 347 of the 349 environmental Premium projects (2 lorem-ipsum placeholder rows dropped), each with a challenge tag, status and dates. Organizations get a stable `ORG-xxxxxxxx` reference, and organization and person names in the text are replaced (`NAME_REPLACEMENTS` in `peers.py`). The owning account is stored only as a salted hash (`owner_key`) so a producer's own projects can be left out.
- **`producer_profiles.json`**: producer id → country, region, crop, entity type. A stand-in until the producer-record tool (#14) and the Athena tables (#28) exist. Region is the region most of the producer's projects are in; 7 of the 146 sample producers have none.

`tests/test_peers.py` fails if either file is stale, or if an account id or a listed name appears in `peer_projects.json`.

## Producer records (issue #14)

```bash
PYTHONPATH=src uv run python -m fx_data.records   # offline -> producer_records.json
```

One record per sample producer: profile (with certification status), their own Premium projects (placeholder rows left out), and a survey summary. Survey answers are reduced to shares of survey responses from an allowlist of farming, water and practice questions (`YES_NO_FIELDS`, `CHOICE_FIELDS`, `MULTI_FIELDS` in `records.py`). Sensitive questions (harassment, borrowing, medical access, child schooling, committees, income) are never read. A share is only reported when at least 5 **distinct survey responses** answered (a response that picks several options counts once), and a reason is only named if at least 5 responses gave it. Each fact's period is the years of the responses behind it. They are called "survey responses", not "households": about half the sample's survey rows are not household surveys. 22 of 146 producers have survey responses; 14 have enough to summarize.

`tests/test_records.py` fails if `producer_records.json` is stale or a sensitive field is added to the allowlist.
