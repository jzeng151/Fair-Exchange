# Scenarios

One JSON file per scripted demo scenario (#35). Each one is a real sample producer, the turns a tester sends, and what should come out. The turns use the request kinds and actions from [`docs/specs/13-conversation-steps.md`](../../docs/specs/13-conversation-steps.md). They never carry a producer id; the runner sends `producer_id` as the logged-in producer.

| File | Producer | Language | Shows | Expected |
|---|---|---|---|---|
| `colombia-drought-es.json` | Coffee cooperative, Cauca, Colombia | es | Spanish exchange, playback correction, full answer | completed, `internal` |
| `mexico-price-drop-en.json` | Coffee cooperative, Chiapas, Mexico | en | Limited evidence (no price peer projects in the sample) | completed, `internal_and_outward` |
| `vietnam-labor-shortage-en.json` | Furniture factory, Binh Duong, Vietnam | en | Limited evidence (no regional data, no labor peers) | completed, `internal` |
| `honduras-decline-es.json` | Coffee producer, La Paz, Honduras | es | **Decline path**, consent changed before closing, question in the consent step | declined |
| `peru-water-pii-es.json` | Coffee producer, Cajamarca, Peru | es | **PII flag path**: names a person and gives a phone number (both invented) | completed, `pii_flag: true`, text kept |

The first three are the vision doc's required scenarios. The Mexico and Vietnam scenarios have limited evidence because the sample data has only environmental Premium projects.

## Fields

- `producer_id`: a producer in `data/src/fx_data/producer_profiles.json`
- `language`: the language the producer writes in
- `turns`: `{"kind": "start"}`, `{"kind": "message", "text": ...}`, or `{"kind": "action", "action": {"name", "args"}}`
- `expect.tags`: challenge tags the confirmed playback should get (11-tag set)
- `expect.evidence`: `full` or `limited`
- `expect.record`: `status`, `consent_scope`, `feedback`, `pii_flag` of the saved record
- Optional: `consent_history`, `playback_after_correction_mentions`, `summary_keeps_pii_text`

`eval/tests/test_scenarios_and_labels.py` checks every file against the spec's actions and the record rules. Running them end to end needs the conversation steps (#13) and the chat endpoint (#25); a runner can drive the agent entrypoint or the deployed API with these files.

## Labeled set

`../labeled/challenge-tags.json`: 33 producer statements (English and Spanish) with challenge tags, at least two per tag, for tag-accuracy scoring (#36). The tags are drafts (`"labeled_by": "draft"`). A person needs to review each item, correct the tags if needed, and replace `draft` with their handle before the set counts as human-labeled.
