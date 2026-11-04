# Spec: Producer-record tool (#14)

Status: approved for build, 2026-11-04. Revised 2026-11-04: survey items are per-question summaries, not one item per response.

## Problem Statement

FEX's answer is generic unless it knows this producer's history: what they funded with Premium, what their surveys say and how they are certified. That history must come only from this producer's own records. The sample survey data also holds sensitive fields (harassment, borrowing, medical access) that FEX must never surface.

## Solution

A data tool that returns this producer's Premium projects, an allowlisted set of survey fields, and certification context. It is scoped by the producer ID from the request context and follows the shared data tool contract ([#17 spec](17-standards-grounding.md)).

## User Stories

1. As a producer, I want FEX to know what my organization already funded with Premium, so that its answer builds on what we have done.
2. As a producer, I want FEX to use my survey context, so that the answer fits our situation.
3. As a producer with no survey data, I want FEX to still work, so that missing surveys do not block me.
4. As a producer, I want sensitive survey answers (harassment, borrowing, medical access) never shown or used, so that private answers stay private.
5. As a producer, I want FEX never to show another producer's records, so that my data stays mine.
6. As an FTUSA reviewer, I want each fact from the producer's record cited to the specific project or survey, so that I can trace it.

## Implementation Decisions

- **Contract.** The shared data tool contract ([#17 spec](17-standards-grounding.md)): no model-settable arguments, producer ID from the request context, `respond` step only, item shape with `source`.

### Producer table (shared contract owned here)

- **One producer list (decided 2026-11-04).** The data work (#7) builds one producer table:
  - FTUSA's anonymized sample producers, keeping their existing IDs;
  - synthetic producers (IDs prefixed `SYN-`) that fill gaps the sample lacks, such as Côte d'Ivoire, cocoa and the scripted scenarios (e.g., a Vietnamese processor), and add deliberate profile contrasts.
- **Shared by everyone.** The data tools, the profile lookup at conversation start ([#13 spec](13-conversation-steps.md)), the test identities and the Athena tables all use this table and its IDs.
- **Storage.** One copy lives in the data bucket as the files behind the Athena tables ([#28 spec](28-athena-sync.md)). The tools load them when the agent starts and filter in memory by producer ID.
- **Profile fields:** country, region (`admin1`), crops and entity type.
- **Normalized vocabulary:**
  - **Crops:** `coffee`, `banana`, `cocoa`, `other`. A producer can have several; the sample's `Cocoa;Coffee` becomes two crops.
  - **Entity types:** `smallholder`, `cooperative`, `cooperative_union`, `hired_labor_farm`, `processor`, `other`.
  - The data work (#7) maps sample values such as `1st Grade`, `Independent Smallholder` and `Estate` to this vocabulary in a reviewed table.
  - A producer's typed entity type correction is mapped to the vocabulary by the small model as a structured choice. `other` is never used for matching.

### Tool behavior

- **Returned items:**
  - **Premium projects:** one item per project. `source` is `Your Premium project: <title> [<project_id>]`. `data` holds category, year, amount and description.
  - **Survey (decided 2026-11-04):** one summary item per allowlisted column or question, across all of this producer's survey responses.
    - An item is returned only when at least 5 distinct survey responses answered that column or question. A multiple-choice answer is named only when at least 5 responses chose it.
    - `source` is `Your <years> survey: <column or question> [<summary_id>]`. `<years>` covers the responses behind the summary. `<summary_id>` is an opaque ID for this producer's summary of that column; it is not a survey response ID.
    - Why: some producers have hundreds of responses (up to 3,951 for one producer in the sample), so one item per response would overflow a model call. And a cooperative's responses come from individual member households, so a single response can identify a member.
  - **Certification context:** certification scope (standards held) only, from `certification_scope_name`. `source` is `Your certification record [<producer_id>]`. Certification status (`certification_status_name`) and audit results are never read, because checking certification status is out of scope (#21).
- **Survey allowlist (default deny).** The tool reads only these coded columns; free-text fields are never read.
  - **Single-choice survey:** response year, `farm_area_ha_nbr`, `has_hired_labor_code`, `harvest_changed_code`, `yield_produced_per_hectare_nbr`, `has_integrated_pest_management_practices_name`, `has_received_fertilizer_training_code`, `has_forest_protection_practices_code`, `has_water_conservation_practices_code`, `has_water_contamination_prevention_practices_code`, `has_soil_conservation_practices_code`, `water_access_sources_name`, `has_noticed_fishing_changes_code`, `adaption_strategies_name`, `future_concerns_name`.
  - **Multiple-choice survey:** only the questions `harvest_change_reason_core`, `income_sources_ms_core` and `ft_benefits_ms_core`.
  - **Everything else is excluded,** including every borrowing, harassment and discrimination, medical, unsafe-conditions, child-enrollment, reporting and leadership-feedback question; pesticide and land-conversion columns (compliance-sensitive); and drinking-water household details.
  - Synthetic survey rows use the same columns.
  - Adding a column needs a spec change.
- **No survey data.** Returns project and certification items only.

## Testing Decisions

- **Seam 1 (agent entrypoint):**
  - producer A gets only A's projects and surveys, even when the model's messages mention producer B's ID or name (negative scope test, #34);
  - a producer without surveys gets projects only;
  - the complete returned payload contains only allowlisted columns, using a fixture row in which every column, including the sensitive ones, is filled;
  - every allowlisted single-choice column (other than response year) and all three multiple-choice questions produce a summary item when 5 or more responses answered them;
  - a column answered by 4 responses produces no item, and a multiple-choice answer chosen by 4 responses is not named;
  - no survey response ID appears in any item;
  - no certification status or audit field appears;
  - every item's `source` reaches session evidence.
- **Prior art:** the existing scope-guard test, and the session-scoped peer-example tool tests.

## Out of Scope

- Answering certification status questions (#21)
- Editing producer data

## Further Notes

### Decisions made while writing this spec

- Producer data has one copy in S3, shared by the tools and Athena, so the two cannot drift apart.
- The survey allowlist above, built from the sample's columns on 2026-11-04. The team should check it in the first PR that uses it.
- Certification data is context only, never status.
