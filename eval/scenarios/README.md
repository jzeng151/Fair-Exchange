# Scenarios

One JSON file per scripted demo scenario (#35), `S1.json` to `S7.json`. Each is a producer from the producer table (#7), the turns a tester sends, and what should come out. The turns use the actions from [`docs/specs/13-conversation-steps.md`](../../docs/specs/13-conversation-steps.md). They never carry a producer id; the runner sends `producer_id` as the logged-in producer.

| ID | Producer | Language | Path | Expected |
|---|---|---|---|---|
| `S1` | Coffee smallholder, Cauca, Colombia | en | Drought; playback correction | completed, `internal`, `full` |
| `S2` | Coffee cooperative, Chiapas, Mexico | es | Price drop | completed, `internal_and_outward`, `full` |
| `S3` | Coffee processor, Dak Lak, Vietnam (synthetic, `SYN-003`) | en | Labor shortage; the regional tool returns nothing | completed, `internal`, `full` |
| `S4` | Coffee producer, La Paz, Honduras | es | **Decline path** — consent changed before closing | declined, `full` |
| `S5` | Cocoa producer, Goh-Djiboua, Côte d'Ivoire | en | **PII flag path** — names a person and gives a phone number (both invented) | completed, `internal`, `pii_flag: true` (`NAME`, `PHONE`), text kept |
| `S6` | Coffee producer, Jinotega, Nicaragua | en | Asks certification status (out of scope), then a labor challenge | completed, `internal`, `full`, `out_of_scope: true` |
| `S7` | Banana grower, El Oro, Ecuador | en | Same tags as S1, different crop and region — distinctness | completed, `internal`, `full` |

S1 to S5 make up the minimum demo run-through (README), with S6 added once its detection is decided. S2 and S4 cover Spanish. S7 shares S1's tags to check the agent keeps distinct producers distinct. S3 has no regional insight because the regional table does not cover Vietnam, but synthetic labor projects give it peer examples (#7), so no scenario currently expects limited evidence.

## Fields

- `scenario_id`: `S1` to `S7`, the spec's required set
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

`eval/tests/test_scenarios_and_labels.py` checks every file against the spec's actions, steps, and record rules. Running them end to end needs the conversation steps (#13) and the chat endpoint (#25); the runner drives the agent entrypoint or the deployed API with these files, waiting for `done` and the end of the response stream between turns.

## Labeled set

`../labeled/challenge-tags.jsonl`: fifteen producer statements (English and Spanish) as JSON lines, each with a `producer_id` from the producer table, two labelers' independent tags (`labeler_a`, `labeler_b`) and the settled `reference` tags, spread across the 11 tags (at least two per tag). They are the reference inputs for tag-accuracy scoring (#36). The two labelers must tag independently without seeing FEX's output, and must not tune prompts against this set before the first eval run is recorded; disagreements are settled by discussion into the `reference` tags. The agreement between the two labelers (mean Jaccard) is reported by the eval harness.
