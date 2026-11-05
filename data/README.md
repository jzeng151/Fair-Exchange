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

## Producer data generator (issue #7)

One set of producer data files, shared by the data tools, the profile lookup, the test logins and Athena ([spec](../docs/specs/07-synthetic-data.md)). It combines FTUSA's sample producers, with their own IDs, and synthetic `SYN-` producers that fill the sample's gaps (Côte d'Ivoire, cocoa, the scripted scenarios) and form contrast pairs.

```bash
uv run --group generator python -m fx_data.generator   # calls Comprehend for new or edited descriptions (AWS credentials)
uv run python -m fx_data.generator --offline           # no AWS; fails if a catalog description has no PII result
```

**Inputs** (`generator_inputs/`, all reviewed by hand):

| File | What |
|---|---|
| `producer_definitions.json` | The synthetic producers: profile, Premium projects with their tags, survey responses (allowlisted columns only), certification scope. Also the scenario producers and the contrast pairs. |
| `vocabulary_map.csv` | Sample crop and structure values to the #14 vocabulary. A value not listed becomes `other` and is listed in the report. |
| `subcategory_tags.csv` | Sample project sub-category to challenge tags. A project whose sub-category is blank or not listed stays out of the peer catalog. |
| `pii_checks.csv` | Comprehend's answer for each catalog description, keyed by its SHA-256. Only descriptions not in the file are sent to Comprehend. |

Plus FTUSA's sample in `docs/olena_data/`.

**Rules:**
- Only sample producers with a crop that maps to `coffee`, `banana` or `cocoa` are kept. Factories are left out.
- A sample producer's region is the most frequent region across its Premium projects (ties go to the alphabetically first), or empty if it has none.
- Countries use the regional table's spelling (`Cote d'Ivoire` becomes `Côte d'Ivoire`).
- Project IDs (`PRJ-`) and catalog IDs (`CAT-`) are separate hashes, so a producer's own project can't be linked to its catalog entry.
- A description is a PII hit when Comprehend finds a `NAME`, `PHONE`, `EMAIL` or `ADDRESS` with a score of 0.8 or more (the #20 rule). A hit leaves the project out of the catalog.
- No randomness: the same inputs give byte-identical files.

**Outputs** (`src/fx_data/generated/`, one folder per table so each maps to an S3 prefix):

| Table | Rows |
|---|---|
| `producers` | `producer_id`, `country`, `admin1`, `crops`, `entity_type`, `origin` (`sample` or `synthetic`) |
| `premium_projects` | `project_id`, `producer_id`, `title`, `category`, `sub_category`, `tags`, `start_year`, `amount` (empty for sample rows), `description` |
| `survey_responses` | one row per response: the #14 allowlisted columns, `response_year`, and one list per allowed multiple-choice question |
| `certifications` | `producer_id`, `certification_scope` (status is never read, #21) |
| `peer_catalog` | the publishable fields (#16), `catalog_id`, `tags`, and the private `owner_producer_id` |

`report.json` lists counts per country, crop and entity type, unmapped values, excluded producers and projects with the reason, projects named "test", and PII hit counts.

**To use FTUSA's own sample:** replace the files in `docs/olena_data/` (same columns), add any new sample values to the two mapping tables, then run the generator with AWS credentials. Check `report.json` for unmapped values and PII hits, hand-edit or accept them, and run `uv run pytest`.

`tests/test_generator.py` runs the rules on a small fixture sample with Comprehend stubbed, and fails if the committed files no longer match the inputs.

**Data bucket export.** `python -m fx_data.export <out_dir>` (run by `infra/deploy.sh`) writes these tables for S3 and the Glue tables in `infra/lib/data-bucket.ts`, with the same fields. The one difference is the survey: `survey_responses` is not exported, only its per-question summaries (`survey_facts`, at least 5 responses each). `certifications` is exported as `certification`. `tests/test_export.py` fails if the Glue columns and the exported fields differ.

### Runtime lookups

- `fx_data.peers`: `ProducerProfiles` (profile by producer ID) and `PeerProjects.find` (#16 ranking: tag, crop and entity type; `other` never counts as a match). `NAME_REPLACEMENTS` replaces organization and person names in catalog descriptions before the PII check.
- `fx_data.records`: `ProducerRecords.items(producer_id)` (#14). Survey answers are summarized per question across the producer's responses, only when at least 5 **distinct survey responses** answered, and a multiple-choice answer is only named if at least 5 responses chose it. The allowlist is `YES_NO_FIELDS`, `CHOICE_FIELDS`, `NUMBER_FIELDS` and `MULTI_FIELDS`; sensitive questions are never copied. A missing number is recorded as 0 in the sample, so 0 is left out of medians.
