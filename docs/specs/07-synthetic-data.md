# Spec: Producer data and synthetic data generator (#7)

Status: approved for build, 2026-11-04.

## Problem Statement

The agent, the tools, the profile lookup, the test logins, Athena and the evals all need one shared list of producers. FTUSA's anonymized sample is realistic, but it has gaps:
- it is thin in cocoa and Côte d'Ivoire;
- it has no Vietnamese processor for the scripted scenario;
- it has no designed contrasts for the "distinct responses" metric;
- its values (`1st Grade`, `Cocoa;Coffee`) don't match the vocabulary the tools use.

The generator is also a handoff deliverable, so FTUSA can rebuild the data.

## Solution

A deterministic generator in the data package builds one set of data files and loads them into S3 and Athena:
- the producer table;
- Premium projects;
- the survey and certification tables;
- the peer catalog.

It combines FTUSA's sample producers, with their existing IDs, with synthetic `SYN-` producers that fill the gaps and create deliberate contrasts. The [#14 spec](14-producer-record-tool.md) owns the producer table contract; this spec defines how it is built.

## User Stories

1. As a tester, I want producers for each scripted scenario (a Colombian coffee smallholder, a Mexican coffee cooperative, a Vietnamese processor and others), so that the demo scripts have real profiles behind them.
2. As an FTUSA reviewer, I want pairs of producers who share a challenge but differ in crop, region or entity type, so that the "distinct responses" metric can be measured.
3. As an FTUSA engineer, I want FTUSA's sample producers kept with their own IDs, so that FTUSA's data shape is preserved and real-sample joins work.
4. As an FTUSA engineer, I want the sample's values mapped to the tools' vocabulary through a reviewed table, so that matching works the same way every time.
5. As an FTUSA engineer, I want the generator to produce the same output from the same input, so that deploys and evals are repeatable.
6. As a producer, I want peer examples drawn from a catalog with fictional names and PII-checked descriptions, so that no organization or person is exposed.
7. As an FTUSA engineer, I want the generator and its loading steps documented, so that we can rebuild the data with our own sample.

## Implementation Decisions

- **Inputs:**
  - FTUSA's sample files in `docs/olena_data/` (producer accounts, Premium projects, surveys);
  - a hand-written scenario file listing the synthetic producers;
  - a reviewed vocabulary mapping table.
- **Synthetic producers:**
  - IDs are `SYN-` plus a stable number.
  - Each is defined in the scenario file with country, region, crops, entity type, and a few Premium projects and survey rows using the allowlisted columns ([#14](14-producer-record-tool.md)).
  - They must cover:
    - a Colombian coffee smallholder in Cauca facing drought;
    - a Mexican coffee cooperative facing a price drop;
    - a Vietnamese processor facing a labor shortage;
    - at least two Côte d'Ivoire cocoa producers;
    - a Honduran or Peruvian Spanish-language producer.
- **Contrasts.** At least three pairs that share a challenge tag but differ in crop, region or entity type. They are listed in the scenario file so evals can find them.
- **Mapping table.** A reviewed CSV maps sample values to the [#14](14-producer-record-tool.md) vocabulary (e.g., `1st Grade` to `cooperative`, `Independent Smallholder` to `smallholder`, `Estate` to `hired_labor_farm`, `Bananas` to `banana`). Unmapped values become `other`, and the generator lists them in its report.
- **Scope of sample rows.** Only sample producers whose crops map to `coffee`, `banana` or `cocoa` go into the producer table. Factories and apparel accounts are excluded.
- **Outputs:**
  - JSON lines files for the producer table, Premium projects, survey responses (allowlisted columns only) and certification scope;
  - the peer catalog;
  - a run report covering counts per country, crop and entity type, unmapped values and excluded rows.
- **Peer catalog build:**
  - Every eligible project gets a fictional organization name from a fixed list and an opaque `catalog_id`.
  - Only the publishable fields ([#16](16-peer-example-tool.md)) are copied.
  - Each description is checked with Comprehend PII detection. A project with a hit is left out and listed in the report for hand-editing.
  - This step needs AWS credentials and runs as part of the generator, not at agent start.
- **Determinism.** A fixed random seed; the same inputs give byte-identical outputs.
- **Loading.** The deploy script ([#5](05-cdk-stack.md)) uploads the outputs to the data bucket. Glue tables for producers, projects, surveys and certification are defined in CDK over those files for the Journey 3 join ([#28](28-athena-sync.md)).
- **Synthetic text.** Synthetic project descriptions are written in English. They are reworded from sample "reason" text where useful, without copying names.

## Testing Decisions

Generator tests (public function, data package), with the Comprehend step stubbed:
- the same seed and inputs give identical outputs;
- every scenario producer exists with the required profile;
- the listed contrast pairs share a tag and differ as declared;
- the survey output contains only allowlisted columns, even when the input has every column filled;
- excluded sample rows (factories, apparel) are absent;
- unmapped values appear in the report;
- the peer catalog holds only publishable fields and no sample IDs;
- a stubbed PII hit leaves the project out.

Prior art: the existing data package tests.

## Out of Scope

- The regional fact table ([#8](08-regional-fact-table.md))
- Seeded conversation records ([#37](37-seeded-records.md))
