# Scenarios

One JSON file per scripted demo scenario (#35). Each one is a producer from the producer table (#7), the turns a tester sends, and what should come out. The turns use the request kinds and actions from [`docs/specs/13-conversation-steps.md`](../../docs/specs/13-conversation-steps.md). They never carry a producer id; the runner sends `producer_id` as the logged-in producer.

| File | Producer | Language | Shows | Expected |
|---|---|---|---|---|
| `colombia-drought-es.json` | Coffee cooperative, Cauca, Colombia | es | Spanish exchange, playback correction, full answer | completed, `internal` |
| `mexico-price-drop-en.json` | Coffee cooperative, Chiapas, Mexico | en | Full answer from sample peer projects, outward sharing | completed, `internal_and_outward` |
| `vietnam-labor-shortage-en.json` | Coffee processor, Dak Lak, Vietnam (synthetic, `SYN-003`) | en | No regional insight (no regional data for Vietnam) | completed, `internal` |
| `honduras-decline-es.json` | Coffee producer, La Paz, Honduras | es | **Decline path**, consent changed before closing, question in the consent step | declined |
| `peru-water-pii-es.json` | Coffee producer, Cajamarca, Peru | es | **PII flag path**: names a person and gives a phone number (both invented) | completed, `pii_flag: true`, text kept |

The first three are the vision doc's required scenarios. The Vietnam scenario has no regional insight because the regional table does not cover Vietnam, but it still has full evidence: synthetic labor projects give it peer examples (#7). No scenario currently expects limited evidence.

## Fields

- `producer_id`: a producer in the producer table, `data/src/fx_data/generated/producers/producers.jsonl` (#7)
- `language`: the language the producer writes in
- `turns`: `{"kind": "start"}`, `{"kind": "message", "text": ...}`, or `{"kind": "action", "action": {"name", "args"}}`
- `expect.tags`: challenge tags the confirmed playback should get (11-tag set)
- `expect.evidence`: `full` or `limited`
- `expect.record`: `status`, `consent_scope`, `feedback`, `pii_flag` of the saved record
- Optional: `consent_history`, `playback_after_correction_mentions`, `summary_keeps_pii_text`

`eval/tests/test_scenarios_and_labels.py` checks every file against the spec's actions and the record rules. Running them end to end needs the conversation steps (#13) and the chat endpoint (#25); a runner can drive the agent entrypoint or the deployed API with these files.

## Labeled set

`../labeled/challenge-tags.json`: 33 producer statements (English and Spanish) with challenge tags, at least two per tag, for tag-accuracy scoring (#36). Labels were drafted, then reviewed and corrected by a person (`labeled_by`). 19 items carry more than one tag. Spanish items were reviewed from a Google Translate English version and are marked `(via Google Translate)`.
