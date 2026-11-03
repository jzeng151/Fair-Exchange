# Regional-context climate tool (spec-aligned)

The spec-conformant form of the climate work: the agent's **Regional-context
tool** for the "what the data shows" output, built the way the Technical
Environment doc requires.

## Why this shape

The Technical Environment doc rules out live open-data calls in the demo
("pre-extract open data to S3 before the event"; "live API or Earth Engine calls
are not needed"). So this splits into two phases:

| Phase | File | When it runs | What it does |
| ----- | ---- | ------------ | ------------ |
| Pre-extraction | `prepare.py` | once, during prep | Calls CHIRPS + Aqueduct per region, writes a static table |
| Runtime tool | `tool.py` | per agent turn | Reads only the static table; no network |

## Data flow

```
prepare.py  --(CHIRPS + Aqueduct, once)-->  data/regional_climate.json  --(read)-->  tool.py  -->  agent
```

Regions come from the real synthetic producer data (country + admin-1 region),
mapped to representative centroids in `region_centroids.py`.

## Pre-extraction (prep time)

```bash
# all catalogued regions:
python -m regional_context.prepare --out data/regional_climate.json
# or one country (faster):
python -m regional_context.prepare --out data/regional_climate.json --only colombia
```

In the sandbox the output JSON would be uploaded to S3 (and optionally catalogued
in Glue for Athena). Point the tool at a different path with the
`REGIONAL_CLIMATE_TABLE` env var.

## Runtime tool

`regional_climate_tool` is a Strands `@tool` when the SDK is installed; otherwise
it falls back to the plain `get_regional_climate()` function so the logic is
testable without Strands.

```python
from regional_context.tool import get_regional_climate

ctx = get_regional_climate(country="Colombia", region="Cauca", crop="Coffee")
for claim in ctx.claims:
    print(claim.statement, "->", claim.citation.source)
```

### Spec requirements this satisfies

- **No runtime API calls** — the tool only reads the static table.
- **Per-claim citations** — every `ClimateClaim` carries a `Citation`
  (source, detail, retrieval date, URL). Grounding/traceability is a success metric.
- **Scope enforced in the tool** — it matches only `(country, region, crop)` from
  session context and can only return a pre-loaded region. Unknown country →
  `matched: false` with a note, never invented data. (In AgentCore, inject these
  from the session, not from free-form model output.)
- **Pydantic schemas** at the tool boundary (`schemas.py`).

## Files

```
regional_context/
  schemas.py           Pydantic: RegionKey, Citation, ClimateClaim, RegionalClimateContext
  region_centroids.py  (country, region) -> representative (lat, lon)
  prepare.py           one-time pre-extraction -> data/regional_climate.json
  tool.py              runtime Strands tool (reads the static table)
data/regional_climate.json   generated table (currently: Colombia regions)
```

## Still to do for full spec alignment

- Pre-extract the remaining pilot countries (Peru, Honduras, Mexico, etc.) — just
  run `prepare.py` without `--only`.
- Add World Bank commodity prices (the spec names it alongside CHIRPS + Aqueduct);
  that's the market half of the regional-context tool, likely a teammate's piece.
- Wire the static table upload into the CDK/S3 deploy and register in Glue if the
  team wants Athena access.
