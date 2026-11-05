# Mock vs. Real API

The chat has two answer sources. Pick one with the **Answers from: Mock | Real API** switch in the persona card;
the choice is remembered for the browser session. The header badge shows which one actually answered (`MOCK` or
`REAL API`).

| | Mock | Real API |
|---|---|---|
| Who writes the answer | This UI (`exchange/engine.py`): canned topics, optionally phrased by Bedrock (`USE_BEDROCK=1`) | The real FEX agent (`agent/`), through the Fair Exchange chat API (`api/`) |
| Data behind it | Made-up facts in `engine.py` | The project's sample data: producer records, regional facts, peer projects, APS/FPS clauses (`data/`) |
| Conversation | One question, one answer | The agent's steps: intake questions → playback → cited answer → consent → feedback → closed |
| Citations | Fixed labels | The sources and standard clauses the agent's tools returned, checked by its citation verifier |
| Saved record | None | The agent saves a record on consent (locally to a folder, deployed to DynamoDB) |
| Personas | All | Producers only; consumers stay on Mock (the agent serves producers) |

Both use sample data. The difference is whether the answer is made up here or comes from the real agent.

## How the code fits together

```
browser (exchange/static/js/chat.js)
  │  POST /api/chat {message, action?}
  ▼
Django (exchange/views.py: chat, api_chat → _live_turn)
  │  Mock: engine.respond()          Real API: exchange/fex_live.py
  ▼                                    │  POST /conversations, /conversations/{id}/messages, /actions  (NDJSON)
                                       ▼
                            Fair Exchange chat API (api/: local server or API Gateway + Lambda)
                                       ▼
                            FEX agent (agent/: local server or Bedrock AgentCore Runtime)
                                       ▼
                            tools: producer record, regional context, peer examples, standards
```

- **`exchange/fex_live.py`** is the only code that talks to the chat API. `start`, `message` and `action` send
  one request each and return the turn's events. `to_answer` turns those events into the shape the page already
  renders: `text` events become the reply, `claim` events become bullet points plus their citations, and the
  `actions` event becomes the buttons for the agent's next step (✓ confirm playback, save or don't save,
  feedback, end).
- **Identity** is the project's sign-in stand-in ([`docs/specs/11-identity.md`](../../../docs/specs/11-identity.md)).
  Each producer persona has a `fex_producer_id` in `exchange/catalog.py`: a scenario producer from
  [`eval/scenarios/`](../../../eval/scenarios/). The UI sends it as `x-demo-producer-id`, and also sends
  `x-demo-passcode` for the deployed API. The agent's tools read only that producer's data.

  | Persona | Scenario producer |
  |---|---|
  | Mateo Herrera (coffee, Mexico) | `mexico-price-drop-en` |
  | Luz Ramírez (coffee, Colombia) | `colombia-drought-es` |
  | Rosa Castillo (seafood, Peru) | `peru-water-pii-es`. The sample producer grows coffee, so Real API answers are about coffee |
  | Fatou Fofana (rice, Côte d'Ivoire) | `cote-divoire-cocoa-pii-fr`. The sample producer grows cocoa |
- **Conversations:** loading a chat page in Real API mode opens a new conversation (`POST /conversations`) and
  keeps its ID in the Django session. Typed text is sent as a message; during playback the agent treats it as a
  correction. Buttons send actions. **New chat** starts a fresh conversation; **Delete conversation** first ends the
  current one with the agent.
- **If the API fails**, the turn is answered from Mock with a ⚠ note saying why, so a demo never dead-ends.
- **Weather:** the location card shows live weather from Open-Meteo (no key needed). It's always tried in Real
  API mode, and in Mock mode when `USE_LIVE_WEATHER=1` (the default). The card says `Live · Open-Meteo` or
  `Sample weather`. The agent's own answers use its regional data (CHIRPS rainfall, WRI Aqueduct), not this feed.

## Connect to the agent on your machine (no AWS)

Terminal 1, from the repository root. This starts the real agent and the real chat API on port 3000, with the
deterministic demo model instead of Claude:

```bash
bash scripts/e2e/run_local.sh --web      # keeps the chain running; Ctrl-C stops it
```

Terminal 2:

```bash
cd ui/sada
FEX_API_URL=http://127.0.0.1:3000 bash run.sh     # or set FEX_API_URL in .env
```

Open http://localhost:8010, pick a producer, and switch **Answers from** to **Real API**. The demo model gives fixed
replies: it asks three intake questions, then plays back what it heard. It doesn't detect languages the way Claude
does. To use real Claude through Bedrock, start the chain with `FEX_DEMO_MODELS=0` (needs AWS credentials, and
`FEX_STANDARDS_KB_ID` for the standards Knowledge Base; see the root README).

## Connect to the deployed agent

`infra/deploy.sh` deploys the agent runtime and the chat API (see
[`docs/handoff/02-deploy.md`](../../../docs/handoff/02-deploy.md)). Two of its stack outputs are needed:

```bash
aws cloudformation describe-stacks --stack-name FairExchange \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl' || OutputKey=='DemoPasscodeSecretArn']"
aws secretsmanager get-secret-value --secret-id <DemoPasscodeSecretArn> --query SecretString --output text
```

Then, in `ui/sada/.env`:

```bash
export FEX_API_URL="<ApiUrl>"
export FEX_DEMO_PASSCODE="<the passcode>"
export DATA_SOURCE="live"        # optional: open chats in Real API mode by default
```

The deployed API accepts only the scenario producers on its allow-list (`DEMO_PRODUCER_IDS`), and the personas
above use exactly those. The calls go from the Django server, not the browser, so CORS doesn't apply and the
passcode never reaches the page.

## Deploy this UI

There's no deploy script for this UI yet. It's a plain Django app, so it runs anywhere Python 3.12 runs:

```bash
cd ui/sada
.venv/bin/python -m pip install -r requirements.txt
DJANGO_DEBUG=0 .venv/bin/python manage.py collectstatic --noinput
DJANGO_DEBUG=0 DJANGO_SECRET_KEY=<random> CSRF_TRUSTED_ORIGINS=https://<your host> \
  FEX_API_URL=<ApiUrl> FEX_DEMO_PASSCODE=<passcode> \
  .venv/bin/gunicorn config.wsgi --bind 0.0.0.0:8010 --timeout 300
```

Keep `--timeout` at least `FEX_API_TIMEOUT` (300 seconds by default): an answer turn with real Claude can take a
while, and the request waits for the whole turn.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `DATA_SOURCE` | `mock` | Which source a new browser session starts with: `mock` or `live` |
| `FEX_API_URL` | empty | The chat API. Empty: Real API mode shows a notice and answers from Mock |
| `FEX_DEMO_PASSCODE` | empty | The deployed API's demo passcode. Not needed locally |
| `FEX_API_TIMEOUT` | `300` | Seconds to wait for one turn |
| `USE_LIVE_WEATHER` | `1` | Live Open-Meteo weather in Mock mode too |
| `USE_BEDROCK` | `0` | Mock mode only: phrase the canned evidence with Bedrock (`BEDROCK_MODEL_ID`) |

## Known limits

- Ratings, the share-data card and its points are this UI's own features. They aren't sent to the agent. The
  agent's consent and feedback buttons are the ones that reach the saved record.
- The share card's "How others used it" figures are sample numbers.
- Deleting a conversation removes it from the screen and ends it with the agent. The chat API has no delete
  route, so a record the producer chose to save stays saved.
