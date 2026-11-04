# Spec: Regional fact table (#8)

Status: approved for build, 2026-11-04. Merged code differs from this spec (#53). Decided 2026-11-04: the spec wins, and the code changes to match in the retro review.

## Problem Statement

"What the data shows for your region" is one of the two things FEX promises a producer. The sandbox has no live access to climate or market data, and runtime scraping is prohibited. Without a prepared, citable table, the regional-context tool has nothing to return, or returns numbers nobody can trace.

## Solution

A small, pre-extracted table of regional facts for the priority countries and crops. It is drawn from CHIRPS rainfall, the Aqueduct water risk atlas and World Bank commodity prices, plus other open datasets where useful. Every row names its dataset, period and link. Hand-curated rows are marked as a stand-in.

## User Stories

1. As a producer in a priority country, I want FEX to show what rainfall, water stress or price data says for my region and crop, so that I see evidence about my own situation.
2. As a producer, I want every number to name its dataset and period, so that I can check it.
3. As an FTUSA reviewer, I want hand-curated stand-in facts labeled as such, so that they are not mistaken for extracted data.
4. As an FTUSA engineer, I want the table versioned in the repo, so that the demo never depends on a live data source.
5. As an FTUSA engineer, I want each fact mapped to challenge tags, so that the tool returns facts relevant to the producer's challenge.

## Implementation Decisions

- **Coverage.** Peru, Côte d'Ivoire, Colombia, Honduras and Mexico; coffee, banana and cocoa.
  - Region rows (first administrative level, e.g. Cauca) wherever producers in the producer table are located ([#14 spec](14-producer-record-tool.md)), plus country rows.
  - Prices may be `global` benchmark rows.
- **Columns:**

| Column | Meaning |
|---|---|
| `fact_id` | Stable ID |
| `scope` | `region`, `country` or `global` (e.g., World Bank Pink Sheet benchmark prices) |
| `country` | ISO 3166-1 alpha-2, empty for `global` rows |
| `admin1` | Region name, set only for `region` rows |
| `crop` | `coffee`, `banana`, `cocoa`, or empty if not crop-specific (e.g., rainfall) |
| `tags` | Challenge tags this fact is relevant to (e.g., rainfall: `climate and weather`, `water`) |
| `indicator` | e.g., `rainfall_anomaly_pct`, `water_stress_score`, `price_usd_per_kg` |
| `value`, `unit` | The number and its unit |
| `comparison` | Plain description of the baseline, e.g., `vs 2010-2020 mean` |
| `period` | e.g., `2024-2025` |
| `source_name` | e.g., `CHIRPS v2.0` |
| `source_url` | Link to the dataset |
| `extracted_at` | Date extracted |
| `curated` | `true` if hand-curated rather than computed from the dataset |

- **Storage.** A CSV in the data package, loaded into memory by the regional-context tool when the agent starts ([#15 spec](15-regional-context-tool.md)). It is not uploaded to S3.
- **Source label.** `<source_name> <indicator>, <admin1, country or "global">, <period> [<fact_id>]`, with ` (curated stand-in)` before the bracket when `curated` is true. Including the indicator and `fact_id` makes each label unique. This is the `source` the tool returns ([#17 spec](17-standards-grounding.md)).
- **Validation.** A loader check rejects rows with unknown countries, crops, tags or empty source fields.
- **Rules.** No runtime scraping or API calls. Extraction happens before the event.

## Testing Decisions

- **Loader tests (data package, public function):**
  - valid rows load;
  - rows with an unknown tag, a missing source, a bad country code, or a `scope` that doesn't fit the country and region fields are rejected;
  - source labels are unique;
  - every priority country has at least one `region` or `country` row, and every priority crop has at least one price row (`global` allowed).
- **Prior art:** the standards loader tests.

## Out of Scope

- Datasets beyond what fits the two days (ERA5, SoilGrids, WDPA, LandMark are optional extras)
- Countries outside the priority list. Producers elsewhere get the limited-evidence path ([#13 spec](13-conversation-steps.md)).
