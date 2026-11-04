# Tool contracts

What each FEX tool takes, returns and guarantees. Code: `agent/src/fex/tools/`. Data: `data/src/fx_data/`.

## Data tool contract (all data tools, #17)

The contract is owned by [`docs/specs/17-standards-grounding.md`](../specs/17-standards-grounding.md). Code: `fex.tools._contract`.

- **No model-settable arguments.** Every data tool is `@tool(context=True)` with no parameters. It reads everything from `tool_context.invocation_state`, which the conversation engine builds in code: `producer_id`, `step`, `entity_type` (a playback correction), `tags`, `summary_english` and `summary_original` (the confirmed playback). A value the model adds anyway is ignored. `agent/tests/test_scope_guard.py` asserts every tool in `ALL_TOOLS` has an empty input schema.
- **Scope.** No producer in the session: the tool returns an error (`PermissionError: No producer in session`). Location and crop come from the producer's profile (`fx_data.peers.ProducerProfiles`, a stand-in until #14 and #28).
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

The decision log records only the codes.

## `get_producer_record()` (#14)

Items with `kind: "producer_record"`: first the profile, then the producer's own Premium projects, then survey facts.

```json
[{"source": "FTUSA producer account (sample data)", "kind": "producer_record",
  "text": "Location on file: Cajamarca, Peru; crop: Coffee; entity type: 1st Grade; certification scope: Producer",
  "period": null, "strength": "exact",
  "data": {"country": "Peru", "region": "Cajamarca", "crop": "Coffee", "entity_type": "1st Grade",
           "certification_scope": "Producer", "supply_chain_role": "Producer"}},
 {"source": "FTUSA Premium project (sample data, own record) PROJ-…", "kind": "producer_record",
  "text": "Your Premium project <name> (Completed): <action>", "period": "<start> to <end>", "strength": "exact",
  "data": {"project_ref": "PROJ-…", "challenge_tag": "water", "name": "…", "challenge": "…", "action": "…",
           "intended_outcome": "…", "status": "Completed", "start_date": "…", "end_date": "…"}},
 {"source": "FTUSA survey responses (sample data)", "kind": "producer_record",
  "text": "96% of 676 survey responses say they use soil conservation practices.", "period": "2021-2026",
  "strength": "exact", "data": {"text": "…", "period": "2021-2026", "responses": 676, "strength": "exact"}}]
```

- The producer's own projects keep their real names and text; it is their own record. Sample placeholder rows (lorem ipsum) are left out. `project_ref` is unique per project and is the same ref the peer table uses. `status` and dates are `null` where the sample cannot tell similar projects apart.
- **Survey answers are summarized, never returned row by row**, and only from an allowlist of farming, water and practice questions (`fx_data.records`). Harassment, borrowing, medical access, child schooling, committees and income questions are never read. A share needs at least 5 **distinct survey responses** (a response that picks several options counts once), and a reason is only named if at least 5 responses gave it. Each fact's `period` is the years of the responses behind that fact. Facts say "survey responses", not "households": about half the sample's survey rows are not household surveys.
- 22 of the 146 sample producers have survey responses; 14 have enough to summarize. Otherwise there are no survey items.
- Unknown producer: an empty list.
- The per-item `[<id>]` source labels are #14 retro work.

## `get_regional_context()` (#15, data from #8)

Items with `kind: "regional"`, one per fact for the producer's region and crop:

```json
[{"source": "CHIRPS v2.0 rainfall (Climate Hazards Center, via SERVIR ClimateSERV)", "kind": "regional",
  "text": "Rainfall near the centre of Cauca, Colombia averaged ...", "period": "2014-2025", "strength": "nearest",
  "data": {"metric": "rainfall_change_pct", "value": -10.4, "unit": "%", "match_level": "region",
           "region": {"country": "Colombia", "region": "Cauca", "crop": "Coffee"}}}]
```

- `data.match_level` is `region` (rainfall, water stress, crop prices) or `country` (crop prices only). No data for the region, or no profile: an empty list. It never substitutes a neighbouring region.
- Strength is `nearest` for climate and water (one point near the region's centre) and `limited` for prices (world benchmarks).
- Tag filtering, unique `[fact_id]` source labels and the 8-item limit are the #15 and #08 retro work.

## `find_peer_examples()` (#16)

Items with `kind: "peer"`, up to 3, best match first, for the confirmed tags:

```json
[{"source": "FTUSA Premium project (sample data, fictionalized) PROJ-2735455E", "kind": "peer",
  "text": "<project name> (Completed, Peru): <action>", "period": "2021-01-01 to 2022-12-31", "strength": "exact",
  "data": {"project_ref": "PROJ-2735455E", "org_ref": "ORG-F1037E8F", "challenge_tag": "water", "crop": "Coffee",
           "entity_type": "1st Grade", "country": "Peru", "region": "San Martin", "subcategory": "Clean Water",
           "name": "...", "challenge": "...", "action": "...", "intended_outcome": "...", "status": "Completed",
           "start_date": "2021-01-01", "end_date": "2022-12-31", "match_score": 1.0}}]
```

- Only projects sharing a confirmed tag. Ranked by crop (0.4), entity type (0.3), same country (0.2), completed (0.1). `strength` is `exact` for a crop and entity type match, `nearest` for one of them, `limited` for the tag only.
- Never the session producer's own projects. At most one project per organization. Organizations are fictionalized; account IDs never appear.
- `intended_outcome` is what the project aimed for, not a recorded result. `status` says whether it was completed; it and the dates are `null` for the few projects the sample cannot tell apart, and FEX should not claim a status for those.
- Empty list: no comparable project. The sample covers environmental projects only.
- The publishable-field list, catalog IDs and `Premium project, <name> [<catalog_id>]` labels are the #16 retro work.

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
| `regional_facts.json` | `fx_data.regional build` (offline) | after `fetch` |
| `peer_projects.json`, `producer_profiles.json` | `fx_data.peers` (offline) | when the sample data changes |
| `producer_records.json` | `fx_data.records` (offline) | when the sample data changes |

The architecture in the [repository README](../../README.md) puts the regional table in S3 and peer search in a Knowledge Base. For the sandbox these ship as package data, like `clauses.json` (#9). Moving them to S3 or a Knowledge Base changes the loaders in `fx_data`, not the tool contracts.
