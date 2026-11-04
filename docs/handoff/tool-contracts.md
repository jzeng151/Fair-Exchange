# Tool contracts

What each FEX tool takes, returns and guarantees. Code: `agent/src/fex/tools/`. Data: `data/src/fx_data/`.

## Scope rule (all tools)

Specs: [#17 data tool contract](../specs/17-standards-grounding.md), [#14](../specs/14-producer-record-tool.md), [#15](../specs/15-regional-context-tool.md), [#16](../specs/16-peer-example-tool.md).

- Every tool is `@tool(context=True)` and takes **no model-settable arguments**. Its input schema has no properties; `agent/tests/test_scope_guard.py` checks every tool in `ALL_TOOLS`. A value the model adds anyway is ignored.
- Everything a tool reads comes from `tool_context.invocation_state`, set by the conversation engine in code, through `fex.tools._scope`:
  - `producer_id` (`session_producer_id`), from the producer's login. None in the session: the tool returns an error (`PermissionError: No producer in session`).
  - `tags` (`session_tags`), the confirmed playback's challenge tags.
  - `entity_type` (`session_entity_type`), the profile value or the producer's correction in playback.
- Location and crop come from the producer's profile (`fx_data.peers.ProducerProfiles`), never from corrections. When the #7 producer table and the Athena tables (#28) exist, swap the loaders in `fx_data`; the tool contracts do not change.

## Step gating (all data tools, #13)

- Data tools run only in the conversation's `respond` step, after the producer confirms the playback. The step comes from `tool_context.invocation_state["step"]`; the model never sets it.
- Every data tool starts with `if refusal := retrieval_refusal(tool_context): return refusal`. Outside `respond`, including when no step is set, it returns `{"refused": true, "reason": "Data tools run only after the producer confirms the playback."}` instead of data.
- Tests that call a tool directly get `step: "respond"` from `tests/tool_harness.call_tool` unless they pass another step (or `step=None` for none).

## Result shape (all data tools)

Each tool returns a **list of items**. Nothing found is an empty list, not an error.

| Field | Meaning |
|---|---|
| `source` | Citable label, unique per fact or record, ending in the item's stable ID in brackets. Copy it exactly into `Citation.source`. |
| `kind` | `producer_record`, `regional` or `peer` |
| `text` | A plain-English statement of the fact |
| `period` | The time span, or `null` |
| `strength` | `exact`, `nearest` or `limited`. Copy into `Citation.strength`. |
| `data` | Tool-specific fields |

Tools do not choose a standard clause; that comes from the standards tool.

**Feed the verifier:** `evidence.record_tool_result(items)` for each tool's list. The engine does this for every tool result in the `respond` step.

## `get_producer_record()` (#14)

Items, in this order:

- **Certification scope**, one item. `source` is `Your certification record [<producer_id>]`; `data` is `{"certification_scope": …}`. Certification status and audit results are never read (#21).
- **Own Premium projects**, one item per project. `source` is `Your Premium project: <name> [<project_ref>]`; `data` is `{category, sub_category, year, amount, description}`. The sample has no amounts, so `amount` is `null`. The producer's own projects keep their real names and text; it is their own record. Placeholder rows (lorem ipsum) are left out.
- **Survey summaries**, one item per allowlisted column with enough answers. `source` is `Your <years> survey: <column> [SV-…]`; `data` is `{column, responses}`.

```json
[{"source": "Your certification record [7F7F…]", "kind": "producer_record", "text": "Certification scope: Producer.",
  "period": null, "strength": "exact", "data": {"certification_scope": "Producer"}},
 {"source": "Your 2024 survey: has_soil_conservation_practices_code [SV-EEDA42]", "kind": "producer_record",
  "text": "99% of 150 survey responses say they use soil conservation practices.", "period": "2024",
  "strength": "exact", "data": {"column": "has_soil_conservation_practices_code", "responses": 150}}]
```

- **Survey answers are summarized, never returned row by row**, and only from the #14 allowlist (`fx_data.records`). A share needs at least 5 **distinct survey responses**, and a reason is only named if at least 5 responses gave it. Each item's `period` is the years of the responses behind it.
- **Differs from the #14 spec:** the spec asks for one item per column per survey response, with the survey response ID in the source. This tool keeps the aggregated summaries (one item per column, ID `SV-` + hash of producer and column), because single responses could be picked out and the sample has up to 683 responses per producer. Open question for the spec owner.
- 12 of the 146 sample producers have enough survey answers to summarize. The rest get certification and project items only.
- Unknown producer: `[]`.

## `get_regional_context()` (#15, data from #8)

Rows of `regional_facts.csv` (#8) whose tags overlap the confirmed tags and whose crop, if any, is one of the profile crops:

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

Prices are world benchmarks, not farm-gate prices; their text says so. Uncovered country, no matching tag, or unknown producer: `[]`.

## `find_peer_examples()` (#16)

Peer catalog projects (`peer_projects.json`) that share a confirmed tag, excluding the session producer's own projects:

| Matches | `strength` |
|---|---|
| tag + a profile crop + entity type | `exact` |
| tag + one of crop or entity type | `nearest` |
| tag only | `limited` |

At most 3 items, strongest first, ties broken by most recent start year. At most one project per organization (an addition to the spec, so one group cannot fill every slot).

```json
[{"source": "Premium project, Ébano Farmers' Cooperative [PROJ-2E54C093]", "kind": "peer",
  "text": "Ébano Farmers' Cooperative (Coffee, Afghanistan) funded a Premium project starting in 2025: …",
  "period": "2025", "strength": "nearest",
  "data": {"organization": "Ébano Farmers' Cooperative", "country": "Afghanistan", "crop": "Coffee", "entity_type": null,
           "category": "Environmental", "sub_category": "Clean Water", "start_year": 2025, "description": "…"}}]
```

- `data` holds only the publishable fields. Organization names are fictional (`fx_data.peers.FICTIONAL_NAMES`), names in descriptions are replaced, and no account or sample project ID appears. `catalog_id` is opaque.
- The catalog's private `owner_key` (a salted hash of the owning account) is used only to leave out the producer's own projects and is never returned.
- Interim build until the #7 generator: descriptions are not yet checked with Comprehend PII detection, and crop and entity type use the sample's raw values rather than the #14 vocabulary.
- The sample covers environmental projects only, so market, labor, health and similar challenges return `[]` today.

## Data files (shipped inside `fx_data`)

| File | Built by | Rebuild |
|---|---|---|
| `regional_sources.json` | `fx_data.regional fetch` (network) | when adding regions or refreshing data |
| `regional_facts.csv` | `fx_data.regional build` (offline; validated, #8 columns) | after `fetch` |
| `peer_projects.json`, `producer_profiles.json` | `fx_data.peers` (offline) | when the sample data changes |
| `producer_records.json` | `fx_data.records` (offline) | when the sample data changes |

The architecture in the [repository README](../../README.md) puts the regional table in S3 and peer search in a Knowledge Base. For the sandbox these ship as package data, like `clauses.json` (#9). Moving them to S3 or a Knowledge Base changes the loaders in `fx_data`, not the tool contracts.
