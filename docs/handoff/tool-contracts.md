# Tool contracts

What each FEX tool takes, returns and guarantees. Code: `agent/src/fex/tools/`. Data: `data/src/fx_data/`.

## Scope rule (all tools)

- Every tool is `@tool(context=True)` and gets the producer only from `tool_context.invocation_state["producer_id"]`, through `fex.tools._scope.session_producer_id`. The AgentCore entrypoint sets it from the producer's login.
- No tool has a producer, location or crop parameter, so the model cannot ask for another producer's data. A value the model adds anyway is ignored. `agent/tests/test_scope_guard.py` checks every tool in `ALL_TOOLS`.
- No producer in the session: the tool returns an error (`PermissionError: No producer in session`).
- Location, crop and entity type come from the producer's profile (`fx_data.peers.ProducerProfiles`). Today that is a stand-in built from the sample accounts. When the producer-record tool (#14) and the Athena tables (#28) exist, swap the profile lookup; the tool contracts do not change.

## Citations

Each fact and peer example has a `source` string. That is the value the citation verifier (#17) records from tool results and checks `Citation.source` against, so FEX must copy it unchanged into the claim's `Citation.source`. Tools do not choose a standard clause; that comes from `check_standards`. Copy `period` and `strength` into the `Citation` too.

## `get_regional_context()` (#15, data from #8)

**Parameters (model-visible):** none.

**Returns:**

```json
{
  "matched": true,
  "match_level": "region",
  "region": {"country": "Colombia", "region": "Cauca", "crop": "Coffee"},
  "facts": [
    {"text": "Rainfall near the centre of Cauca, Colombia averaged ...",
     "source": "CHIRPS v2.0 rainfall (Climate Hazards Center, via SERVIR ClimateSERV)",
     "metric": "rainfall_change_pct", "value": -10.4, "unit": "%",
     "period": "2014-2025", "strength": "nearest"}
  ],
  "note": null
}
```

| `match_level` | Meaning | `facts` |
|---|---|---|
| `region` | The producer's region is in the table | rainfall, baseline water stress, projected water stress, plus crop prices |
| `country` | Region not in the table, crop is priced | crop prices only; `note` says so |
| `none` | Nothing known, or no profile | empty; `note` says so |

It never substitutes a neighbouring region. Strength is `nearest` for climate and water (one point near the region's centre) and `limited` for prices (world benchmarks, not farm-gate prices).

**Feed the verifier:** `evidence.record_tool_result(result["facts"])`.

## `find_peer_examples(challenge)` (#16)

**Parameters (model-visible):** `challenge`, one of the 11 challenge tags (`fex.models.ChallengeTag`). Anything else is rejected by Strands before the tool runs.

**Returns:** a list of up to 3 projects, best match first:

```json
[{"project_ref": "PROJ-2735455E", "org_ref": "ORG-F1037E8F",
  "source": "FTUSA Premium project (sample data, fictionalized) PROJ-2735455E",
  "challenge_tag": "water", "crop": "Coffee", "entity_type": "1st Grade",
  "country": "Peru", "region": "San Martin", "subcategory": "Clean Water",
  "name": "...", "challenge": "...", "action": "...", "intended_outcome": "...",
  "status": "Completed", "start_date": "2021-01-01", "end_date": "2022-12-31",
  "match_score": 1.0}]
```

- Only projects with the same challenge tag. Ranked by crop (0.4), entity type (0.3), same country (0.2), completed (0.1).
- Never the session producer's own projects. At most one project per organization.
- Organizations are fictionalized; account ids never appear.
- `intended_outcome` is what the project aimed for. The sample data has no recorded results, so FEX must not describe it as what happened. `status` says whether the project was completed.
- Empty list: no comparable project. FEX should say so rather than invent one. The sample covers environmental projects only, so market, labor, health and similar challenges return nothing today.

**Feed the verifier:** `evidence.record_tool_result(result)`.

## Data files (shipped inside `fx_data`)

| File | Built by | Rebuild |
|---|---|---|
| `regional_sources.json` | `fx_data.regional fetch` (network) | when adding regions or refreshing data |
| `regional_facts.json` | `fx_data.regional build` (offline) | after `fetch` |
| `peer_projects.json`, `producer_profiles.json` | `fx_data.peers` (offline) | when the sample data changes |

The architecture in the [repository README](../../README.md) puts the regional table in S3 and peer search in a Knowledge Base. For the sandbox these ship as package data, like `clauses.json` (#9). Moving them to S3 or a Knowledge Base changes the loaders in `fx_data`, not the tool contracts.
