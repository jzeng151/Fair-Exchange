# Scenarios

One JSON file per scripted demo scenario (#35), `S1.json` to `S7.json`. Each is a producer from the producer table (#7), the turns a tester sends, and what should come out. The turns use the actions from [`docs/specs/13-conversation-steps.md`](../../docs/specs/13-conversation-steps.md). They never carry a producer id; the runner sends `producer_id` as the logged-in producer.

| ID | Producer | Language | Path | Expected |
|---|---|---|---|---|
| `S1` | `SYN-001`: coffee smallholder, Cauca, Colombia | en | Drought; playback correction | completed, `internal`, `full` |
| `S2` | `SYN-002`: coffee cooperative, Chiapas, Mexico | es | Price drop | completed, `internal_and_outward`, `full` |
| `S3` | `SYN-003`: coffee processor, Dak Lak, Vietnam | en | Labor shortage; the regional tool returns nothing | completed, `internal`, `full` |
| `S4` | `SYN-004`: coffee cooperative, Copan, Honduras | es | **Decline path**: consent changed before closing | declined, `full` |
| `S5` | `SYN-005`: cocoa cooperative, Bas-Sassandra, Côte d'Ivoire | en | **PII flag path**: names a person and gives a phone number (both invented) | completed, `internal`, `pii_flag: true` (`NAME`, `PHONE`), text kept |
| `S6` | `SYN-006`: cocoa smallholder, Goh-Djiboua, Côte d'Ivoire | en | Asks certification status (out of scope), then a labor challenge | completed, `internal`, `full`, `out_of_scope: true` |
| `S7` | `SYN-005`: cocoa cooperative, Bas-Sassandra, Côte d'Ivoire | en | Same tags as S1, different crop, region and entity type: distinctness | completed, `internal`, `full` |

The producers are #7's synthetic producers, listed once in `scenario_producers` in [`data/generator_inputs/producer_definitions.json`](../../data/generator_inputs/producer_definitions.json); a test keeps the files and that list in step. S5 and S7 share a producer, so the web picker keys cards by scenario, not producer. S1 to S5 make up the minimum demo run-through (README), with S6 added once its detection is decided. S2 and S4 cover Spanish. S3 has no regional insight because the regional table does not cover Vietnam, but synthetic labor projects give it peer examples (#7), so no scenario currently expects limited evidence.

Only S1 to S7 sit at the top of this folder: the web's Live FEX picker and the demo sign-in allow-list (`infra/lib/chat-api.ts`) read it.

## Contrast runs

The distinctness check (#36) compares #7's contrast pairs, each producer with its own run. S1 to S7 cover `SYN-001`, `SYN-002`, `SYN-003`, `SYN-005` and `SYN-006` (S6 is C3's run). The other two producers have files in [`contrast/`](contrast/), named after their pair:

| Pair | Producers (runs) | Shared challenge | Differ in |
|---|---|---|---|
| C1 | `SYN-001` (S1), `SYN-005` (S7) | climate and weather | crop, region, entity type |
| C2 | `SYN-002` (S2), `SYN-007` (`contrast/C2-SYN-007.json`) | market and price | crop, region, entity type |
| C3 | `SYN-003` (S3), `SYN-006` (S6) | labor and migration | crop, region, entity type |
| C4 | `SYN-001` (S1), `SYN-008` (`contrast/C4-SYN-008.json`) | climate and weather | entity type only, so C4 is judged on the reviewer mark alone |

## Fields

- `scenario_id`: `S1` to `S7`, the spec's required set; contrast runs use `<pair>-<producer>`, the file's name
- `producer_id`: a producer in the producer table, `data/src/fx_data/generated/producers/producers.jsonl` (#7)
- `language`: the language the producer writes in (`en` or `es`)
- `title`: a human-readable description, shown by the web's Live FEX picker
- `turns`: an ordered list; each entry is either `{"message": text}` or `{"action": {"name", "args"}}`, and each names the step its response stream ends in (`expect_step`: `intake`, `playback`, `respond`, `consent`, `feedback`, `closed`). The last turn is always the `end` action.
- `intake_replies`: scripted answers the runner sends, in order, when FEX asks more intake questions than the turns cover; when they run out it sends "That's all I can add."
- `expected.record_status`: `completed` or `declined`
- `expected.consent_scope`: `internal`, `internal_and_outward`, or `declined`
- `expected.evidence`: `full` or `limited`
- `expected.pii_flag` / `expected.pii_entity_types`: whether the record is flagged and the entity types (`NAME`, `PHONE`, `EMAIL`, `ADDRESS`)
- `expected.tags`: challenge tags the confirmed playback should get (11-tag set)
- `expected.out_of_scope`: whether an out-of-scope request occurs. The `#21` scope detector is "Not decided" and defaults to in-scope, so until it lands the runner checks only the in-scope part of S6.

`eval/tests/test_scenarios_and_labels.py` checks every file against the spec's actions, steps, record rules and #7's producer lists. `eval/tests/test_scenario_runs.py` drives every run through the agent entrypoint with the deterministic demo model and a fake PII scanner, checking each turn's step and allowed actions and every expected outcome except tags (seam 1, #35).

## Labeled set

`../labeled/challenge-tags.jsonl`: fifteen producer statements (English and Spanish) as JSON lines, each with a `producer_id` from the producer table, two labelers' independent tags (`labeler_a`, `labeler_b`) and the settled `reference` tags, spread across the 11 tags (at least two per tag). They are the reference inputs for tag-accuracy scoring (#36). The two labelers must tag independently without seeing FEX's output, and must not tune prompts against this set before the first eval run is recorded; disagreements are settled by discussion into the `reference` tags. The agreement between the two labelers (mean Jaccard) is reported by the eval harness.
