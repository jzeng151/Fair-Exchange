# Tool contracts

What each FEX tool takes, returns and guarantees. Code: `agent/src/fex/tools/`. Data: `data/src/fx_data/`.

## Data tool contract (all data tools, #17)

The contract is owned by [`docs/specs/17-standards-grounding.md`](../specs/17-standards-grounding.md). Code: `fex.tools._contract`.

- **No model-settable arguments.** Every data tool is `@tool(context=True)` with no parameters. It reads everything from `tool_context.invocation_state`, which the conversation engine builds in code: `producer_id`, `step`, `entity_type` (a playback correction), `tags`, `summary_english` and `summary_original` (the confirmed playback). A value the model adds anyway is ignored. `agent/tests/test_scope_guard.py` asserts every tool in `ALL_TOOLS` has an empty input schema.
- **Scope.** No producer in the session: the tool returns an error (`PermissionError: No producer in session`). Location and crop come from the producer's profile (`fx_data.peers.ProducerProfiles`, from the producer table the #7 generator builds).
- **Step gating (#13).** Outside `respond`, including when no step is set, a data tool returns `{"refused": true, "reason": "Data tools run only after the producer confirms the playback."}` instead of data.
- **Result shape.** A list of items, each `{source, kind, text, period, strength, data}`:
  - `source`: the citable label. FEX copies it unchanged into `Citation.source`.
  - `kind`: `producer_record`, `regional`, `peer` or `standard`.
  - `strength`: `exact`, `nearest` or `limited`. `data`: tool-specific fields.
  - Nothing found: an empty list, which leads to the limited-evidence path.
- **Session evidence.** `run_data_tool` adds each item's `source` and `kind` (and, for standards, the clause ID) to the conversation's `SessionEvidence` as it returns them. The verifier accepts only those sources and clauses.
- **Backstop.** After the model's retrieval call, the engine calls any data tool the model skipped through the same `run_data_tool`, and logs `{kind: "tool", code: "tool_backstopped", refs: [tool name]}` in the decision log. Claims are written only after that, from every item returned.
- Tests that call a tool directly get `step: "respond"` from `tests/tool_harness.call_tool` unless they pass another step (or `step=None` for none).

## Citations

A claim passes the verifier (`fex.verifier.check_claim`) only if:

| Rule | Reason code |
|---|---|
| its `source` was returned by a data tool in this conversation | `unknown_source` |
| insights cite `producer_record` or `regional` sources; peer examples cite `peer` sources | `wrong_source_kind` |
| its `standard_clause` exists in APS or FPS | `unknown_clause` |
| ... and was returned by `find_standards` in this conversation | `clause_not_retrieved` |
| its text has no directive phrase (`fex.tone.DIRECTIVE_PHRASES`, English and Spanish) | `directive_language` |
| a claim line that cannot be parsed (#18) | `malformed` |

The decision log records only the codes, with the claim's bracketed source ID and clause ID as refs. A ref
that is not an ID (`fex.models.DECISION_REF`) is left out, so model-written text never reaches the record.

## `get_producer_record()` (#14)

Items with `kind: "producer_record"`, built by `fx_data.records.ProducerRecords.items`, in this order:

- **Certification scope**, one item. `source` is `Your certification record [<producer_id>]`; `data` is `{"certification_scope": …}`. Certification status and audit results are never read (#21).
- **Own Premium projects**, one item per project. `source` is `Your Premium project: <title> [<project_id>]`; `data` is `{category, sub_category, year, amount, description}`. The sample has no amounts, so `amount` is `null`. The producer's own projects keep their real names and text; it is their own record. Placeholder rows (lorem ipsum) are left out.
- **Survey summaries**, one item per allowlisted column with enough answers. `source` is `Your <years> survey: <column> [SV-…]`; `data` is `{column, responses}`.

```json
[{"source": "Your certification record [7F7F…]", "kind": "producer_record", "text": "Certification scope: Producer.",
  "period": null, "strength": "exact", "data": {"certification_scope": "Producer"}},
 {"source": "Your Premium project: environmental plan [PROJ-8085A49F]", "kind": "producer_record",
  "text": "Your Premium project \"environmental plan\", started 2024: …", "period": "2024", "strength": "exact",
  "data": {"category": "Environmental", "sub_category": "…", "year": 2024, "amount": null, "description": "…"}},
 {"source": "Your 2024 survey: has_soil_conservation_practices_code [SV-EEDA42]", "kind": "producer_record",
  "text": "99% of 150 survey responses say they use soil conservation practices.", "period": "2024",
  "strength": "exact", "data": {"column": "has_soil_conservation_practices_code", "responses": 150}}]
```

- **Survey answers are summarized, never returned row by row**, and only from the #14 allowlist (`fx_data.records`). A share needs at least 5 **distinct survey responses** (a response that picks several options counts once), and a reason is only named if at least 5 responses gave it. Each item's `period` is the years of the responses behind it. Items say "survey responses", not "households": about half the sample's survey rows are not household surveys.
- **Differs from the #14 spec:** the spec asks for one item per column per survey response, with the survey response ID in the source. This tool keeps the aggregated summaries (one item per column, ID `SV-` + a hash of producer and column), because single responses could be picked out and the sample has up to 683 responses per producer. Open question for the spec owner.
- 22 of the 146 sample producers have survey responses; 12 have enough to summarize. The rest get certification and project items only.
- Unknown producer: an empty list.

## `get_regional_context()` (#15, data from #8)

Rows of `regional_facts.csv` (#8) whose tags overlap the confirmed tags and whose crop, if any, is one of the profile crops (`fx_data.regional.normalize_crops`):

| Row scope | Qualifies when | `strength` |
|---|---|---|
| `region` | `country` and `admin1` match the profile | `exact` |
| `country` | `country` matches (the average of that country's regions in the table) | `nearest` |
| `global` | always (world benchmark prices) | `limited` |

At most 8 items: region rows, then country, then global. It never substitutes a neighbouring region. `data` is the CSV row.

```json
[{"source": "CHIRPS v2.0 rainfall anomaly, Cauca, Colombia, 2024-2025 [RF-F8C4E1]", "kind": "regional",
  "text": "Rainfall near the centre of Cauca, Colombia in 2024-2025 was 11.5% below the 2014-2023 mean (1,861 mm vs 2,103 mm a year).",
  "period": "2024-2025", "strength": "exact",
  "data": {"fact_id": "RF-F8C4E1", "scope": "region", "country": "CO", "admin1": "Cauca", "crop": "",
           "tags": "climate and weather;water", "indicator": "rainfall_anomaly_pct", "value": "-11.5", "unit": "%", "…": "…"}}]
```

- Prices are world benchmarks, not farm-gate prices; their text says so.
- Uncovered country, no matching tag, or unknown producer: an empty list.

## `find_peer_examples()` (#16)

Peer catalog projects (the generated `peer_catalog` table, #7) that share a confirmed tag, excluding the session producer's own projects:

| Matches | `strength` |
|---|---|
| tag + a profile crop + entity type (the corrected one if the producer corrected it) | `exact` |
| tag + one of crop or entity type | `nearest` |
| tag only | `limited` |

At most 3 items, strongest first, ties broken by most recent start year. At most one project per organization (an addition to the spec, so one group cannot fill every slot).

```json
[{"source": "Premium project, Higuera Producers' Group [PROJ-295DB6A0]", "kind": "peer",
  "text": "Higuera Producers' Group (1st Grade, Coffee, Colombia) funded a Premium project starting in 2024: …",
  "period": "2024", "strength": "exact",
  "data": {"organization": "Higuera Producers' Group", "country": "Colombia", "crop": "Coffee", "entity_type": "1st Grade",
           "category": "Environmental", "sub_category": "Clean Water", "start_year": 2024, "description": "…"}}]
```

- `data` holds only the publishable fields. Organization names are fictional (`fx_data.peers.FICTIONAL_NAMES`), names in descriptions are replaced, and no account or sample project ID appears. `catalog_id` is opaque.
- The catalog's private `owner_producer_id` is used only to leave out the producer's own projects and is never returned (#7, #16 specs).
- Interim build until the #7 generator: descriptions are not yet checked with Comprehend PII detection, and crop and entity type use the sample's raw values rather than the #14 vocabulary.
- Empty list: no comparable project. The sample covers environmental projects only, so market, labor, health and similar challenges return nothing today.

## `find_standards()` (#17)

Items with `kind: "standard"`: the top 5 distinct APS/FPS clauses the standards Knowledge Base returns for the confirmed playback's English summary (the original summary for English conversations) plus its tags.

```json
[{"source": "APS 3.6.1", "kind": "standard", "text": "<clause text>", "period": null, "strength": "exact",
  "data": {"clause_id": "APS 3.6.1", "standard": "APS", "score": 0.61}}]
```

- The retriever is `fex.tools.standards.BedrockKbRetriever`, configured by `FEX_STANDARDS_KB_ID`. The engine passes it in the invocation state; tests pass a fake with the same `ClauseRetriever` interface.
- A claim's `standard_clause` must be one of these clause IDs.
- Knowledge Base deploy: part of `infra/deploy.sh` (see `infra/README.md`).

## Data files (shipped inside `fx_data`)

| File | Built by | Rebuild |
|---|---|---|
| `regional_sources.json` | `fx_data.regional fetch` (network) | when adding regions or refreshing data |
| `regional_facts.csv` | `fx_data.regional build` (offline; validated, #8 columns) | after `fetch` |
| `generated/<table>/<table>.jsonl`: producers, Premium projects, survey responses, certifications, peer catalog | `fx_data.generator` (Comprehend for new descriptions, or `--offline`) | when the sample data or `data/generator_inputs/` change |

The architecture in the [repository README](../../README.md) puts the regional table in S3 and peer search in a Knowledge Base. For the sandbox these ship as package data, like `clauses.json` (#9). Moving them to S3 or a Knowledge Base changes the loaders in `fx_data`, not the tool contracts.

## Scope classification before conversation processing

The live runtime calls `BedrockScopeCheck` before intake, follow-up messages or playback corrections.
It uses `FEX_SMALL_MODEL` through the existing guarded Bedrock model factory, with no data tools.
Only a validated category and language leave the classifier. Code chooses the fixed refusal text.
A service or validation failure preserves the step and asks the producer to retry; the rejected
exchange is excluded from later prompts and PII scans. Decision logs carry fixed scope codes only.
The no-AWS demo remains a scripted stand-in. Retention and disabled recall are unchanged.

Run `cd agent && uv run pytest tests/test_scope_classifier.py tests/test_out_of_scope.py` for
local checks. `scripts/e2e/scope_classifier_smoke.py` exercises synthetic messages against the
configured real Bedrock small model without reading or writing producer records.
