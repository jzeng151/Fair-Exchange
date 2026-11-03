# Peer-example tool

The agent's **Peer-example tool** — the "what others are doing" half of the
response. Given a producer's challenge (as a challenge tag), crop, and entity
type, it finds comparable Premium projects other producers funded and reports
what they did and the outcome they were after, each with a citation.

Built in the same two-phase, spec-aligned shape as `regional_context/`.

## Data flow

```
prepare.py  --(read Premium projects CSV once, tag + fictionalize)-->  data/peer_projects.json  --(read)-->  tool.py  -->  agent
```

Source: `docs/olena_data/pprojects-full-environmental-with-acct-detail.csv`
(349 synthetic environmental Premium projects with the producer's challenge,
what they did, and their goal).

## Pre-extraction (prep time)

```bash
python -m peer_examples.prepare --out data/peer_projects.json
```

Each project is:
- **tagged** with one of the 11 challenge tags (mapped from the environmental
  subcategory, with a keyword fallback for blank subcategories),
- **fictionalized** into stable `PROJ-xxxx` / `ORG-xxxx` refs (the spec permits
  fictionalized org names/IDs for peer projects); the real `account_sk` is kept
  only internally for scope exclusion and is never surfaced,
- carried through with its challenge / action / intended-outcome text.

Current tag distribution (all 349 are environmental projects):

| tag | projects |
| --- | -------- |
| biodiversity and conservation | 206 |
| climate and weather | 74 |
| soil and land | 37 |
| water | 29 |
| social and community | 3 |

## Runtime tool

```python
from peer_examples.tool import get_peer_examples

res = get_peer_examples(
    challenge_tag="water",
    crop="Coffee",
    entity_type="1st Grade",
    exclude_account_sk="<session producer id>",  # never shown their own project
    limit=3,
)
for ex in res.examples:
    print(ex.action, "->", ex.intended_outcome, "[", ex.citation.project_ref, "]")
```

`peer_examples_tool` is a Strands `@tool` when the SDK is installed; otherwise it
falls back to `get_peer_examples()` for testing.

### Matching

Candidates are filtered to the exact `challenge_tag`, then ranked by a weighted
score: tag match (0.5, always present) + crop match (0.3, tolerant of multi-crop
fields like `Cocoa;Coffee`) + entity-type match (0.2). Top `limit` returned.

### Spec requirements this satisfies

- **Scope enforced in the tool** — `exclude_account_sk` (the session producer)
  is filtered out, so a producer never sees their own project as a peer. Verified.
- **Per-claim citations** — each `PeerExample` carries a `ProjectCitation`
  (fictional project/org ref + location/crop/subcategory).
- **No invented precedent** — an unmatched challenge returns `matched: false`
  with a note.
- **Pydantic schemas** at the tool boundary; no runtime CSV parsing (reads the
  pre-extracted table).

## Relationship to the climate tool

Together, the two tools produce the full Journey 1 response:

| Tool | Answers | Matches on |
| ---- | ------- | ---------- |
| `regional_context` | "what the data shows for your region" | country, region, crop |
| `peer_examples` | "what producers in similar situations did" | challenge tag, crop, entity type |

## Files

```
peer_examples/
  schemas.py   Pydantic: PeerQuery, ProjectCitation, PeerExample, PeerExampleResult
  prepare.py   one-time pre-extraction -> data/peer_projects.json
  tool.py      runtime Strands tool (reads the static table)
data/peer_projects.json   generated table (349 tagged projects)
```
