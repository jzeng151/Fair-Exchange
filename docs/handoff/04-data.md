# Data

How Fair Exchange's data is built, and how to replace each piece with FTUSA's own. All of it lives in
the `data/` package (`fx_data`) and ships as package data, so nothing parses source files at runtime.

**Where it is stored on AWS.** The deploy also uploads the producer data to the **data bucket**
(`DataBucketName` output): `python -m fx_data.export` writes one JSON-lines file per table (`producers`,
`certification`, `premium_projects`, `survey_facts`, `peer_catalog`), and Glue tables over the first four
(`DataGlueDatabase` output) let Athena join them with the conversation records (#28). Only allowlisted data is
exported: survey data leaves only as summary facts with at least 5 responses each, never as raw answers. The agent
still reads the packaged copy today; moving the tools to the bucket (#14 "one copy in S3") is the next step.
Details and rebuild commands are in [`data/README.md`](../../data/README.md); the tool-side view is in
[tool contracts](tool-contracts.md#data-files-shipped-inside-fx_data).

## What ships, and how to rebuild it

| File | Built by | Rebuild when |
|---|---|---|
| `clauses.json` | `fx_data.standards_loader` (from the APS/FPS workbooks, [#9](../specs/17-standards-grounding.md)) | the standards workbooks change |
| `regional_sources.json` | `fx_data.regional fetch` (network) | adding regions or refreshing open data ([#8](../specs/08-regional-fact-table.md)) |
| `regional_facts.json` | `fx_data.regional build` (offline) | after a `fetch` |
| `generated/<table>/<table>.jsonl` (producers, Premium projects, survey responses, certifications, peer catalog) | `fx_data.generator` ([#7](../specs/07-synthetic-data.md)) | the sample data or `data/generator_inputs/` change |
| `seeded_records.py` | seeded demo records for the dashboard ([#37](../specs/37-seeded-records.md)) | demo content changes |

Each rebuild has a test that fails if the committed file no longer matches its source (for example
`data/tests/test_standards_lookup.py` for `clauses.json`).

## The synthetic data generator

`fx_data.generator` builds every producer table from FTUSA's sample plus synthetic `SYN-` producers that
fill its gaps and form contrast pairs for the "distinct responses" metric ([spec #7](../specs/07-synthetic-data.md)).
FTUSA rebuilds the data with their own sample by replacing `docs/olena_data/` and running the generator with
AWS credentials (it checks new catalog descriptions with Comprehend). The steps are in
[`data/README.md`](../../data/README.md#producer-data-generator-issue-7). The tool contracts
([Interfaces](03-interfaces.md)) do not change, so swapping the data does not change the agent.

## The vocabulary mapping

FTUSA's source vocabulary (crops, entity types, regions, challenge categories) is mapped to the values
FEX uses — the 11 challenge tags (`fex.models.ChallengeTag`), entity types, and region names that match
the regional fact table. The mapping is two reviewed tables in `data/generator_inputs/`
(`vocabulary_map.csv` for crops and entity types, `subcategory_tags.csv` for project tags), so a new
source vocabulary is a data change, not a code change. Values not in a table are listed in
`generated/report.json`.

## The survey allowlist

`get_producer_record` summarizes survey answers only from an allowlist of farming, water and practice
questions (`fx_data.records`); harassment, borrowing, medical, child-schooling, committee and income
questions are never read. A share needs at least five distinct responses. See
[tool contracts](tool-contracts.md#get_producer_record-14) for the exact rules. Review and adjust the
allowlist for FTUSA's own survey instrument before production.

## The regional fact table

Rainfall (CHIRPS), water stress (Aqueduct) and crop prices (World Bank) are pre-extracted into
`regional_facts.json` for the sandbox ([#8](../specs/08-regional-fact-table.md)). It never substitutes a
neighbouring region; strength is `nearest` for climate/water and `limited` for prices.

## Replacing each with FTUSA data

See the full table in [Stand-in → target mapping](05-stand-in-to-target.md). In short: the regional
table becomes a live or scheduled open-data pipeline; the producer and peer data come from Salesforce
and the warehouse; the standards stay as published clauses. In every case the loaders in `fx_data`
change, and the tool contracts do not.
