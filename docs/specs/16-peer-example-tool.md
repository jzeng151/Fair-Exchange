# Spec: Peer-example tool (#16)

Status: approved for build, 2026-11-04. Merged code differs from this spec (#54). Decided 2026-11-04: the spec wins, and the code changes to match in the retro review. In particular, its model-set `challenge` parameter is removed: tags come from the conversation state.

## Problem Statement

"What others are doing" is the second thing FEX promises. Producers need examples from organizations like theirs, facing the same kind of challenge, and different producers should not all get the same examples. The examples must never expose another producer's private data.

## Solution

A data tool that runs a structured query over the Premium project data for projects funded by other producers. It matches on challenge tag, crop and entity type, and ranks closer matches first. Project data is organization-level and uses fictionalized names.

## User Stories

1. As a producer, I want examples from organizations with my crop and entity type that faced the same challenge, so that the examples are relevant.
2. As a producer, I want the closest matches first and weaker matches labeled, so that I know how comparable each example is.
3. As a producer, I want my own projects excluded from peer examples, so that "what others did" really is others.
4. As a producer, I want examples that differ from another producer's when our profiles differ, so that the answer reflects my situation.
5. As an FTUSA engineer, I want peers shown only by fictionalized organization name, so that no real organization is exposed.

## Implementation Decisions

- **Contract.** The shared data tool contract ([#17 spec](17-standards-grounding.md)).
- **Inputs, all from conversation state:**
  - the confirmed tags;
  - the profile crops;
  - the entity type, including a producer correction ([#13 spec](13-conversation-steps.md)).

  Crops and entity types use the normalized vocabulary in the [#14 spec](14-producer-record-tool.md).
- **Data: the peer catalog.**
  - Built by the data work (#7) from the producer table's Premium projects (FTUSA sample plus synthetic, [#14 spec](14-producer-record-tool.md)). It is loaded from the data bucket.
  - Each project gets a fictional organization name. The vision document confirms that fictionalized names with realistic content are sufficient for organization-level projects.
  - Only the publishable fields below are copied into the catalog.
  - Every description is checked with Comprehend PII detection when the catalog is built. Descriptions with a hit are hand-edited or the project is left out.
  - Projects whose `producer_id` is the session's producer are excluded at query time.
- **Ranking.** A candidate must share at least one confirmed tag. Then:
  - matches tag, a crop and entity type: strength `exact`;
  - matches tag and one of crop or entity type: `nearest`;
  - matches tag only: `limited`.
- **Limit.** At most 3 items, strongest first, ties broken by most recent year.
- **Item.** `source` is `Premium project, <fictional organization name> [<catalog_id>]`, where `catalog_id` is an opaque ID that is not the sample's project or account ID.
- **Publishable fields.** `data` holds only: fictional organization name, country, crop, entity type, category, sub-category, start year and the checked description. No account IDs, contact or personal fields are ever returned.

## Testing Decisions

- **Seam 1 (agent entrypoint) with fixture projects:**
  - the producer's own projects never returned;
  - no field outside the publishable list in any item, and no sample account or project ID;
  - the catalog build leaving out a description with a PII hit;
  - ranking and strength labels;
  - two producers sharing a tag but differing in crop or entity type getting different examples (vision success metric);
  - a corrected entity type used for matching;
  - sources reaching session evidence.

## Out of Scope

- Similarity search over project descriptions. **Future expansion (2026-11-04):** move peer examples onto the standards Knowledge Base ([#17 spec](17-standards-grounding.md)) with tag, crop and entity type as metadata filters, ranked by similarity to the producer's challenge.
