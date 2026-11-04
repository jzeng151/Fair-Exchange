# Start here

## What Fair Exchange is

Fair Exchange (FEX) is a conversational assistant for Fair Trade USA (FTUSA) producers. A producer
describes a challenge in their own language; FEX confirms what it understood, then shares grounded
data and what similar producers have tried, every fact carrying a citation. It never tells the
producer what to do. With the producer's consent, a short, non-narrative record is stored for FTUSA
to review and to aggregate into trends.

The design principles that shaped every part of the system:

- **The producer is in control.** No *record* is stored without consent, and FEX hands the decision back. (Conversation text itself may be held while the conversation runs once persistent memory is on; what happens to it after a decline is still undecided — see the [memory spec](../specs/memory.md) and [open decisions](06-known-limitations.md#open-decisions).)
- **Every fact is traceable.** Claims are shown only after a citation check; unverifiable text is dropped.
- **Scope is enforced in code.** A producer can only ever reach their own data. No tool takes a producer,
  location or crop parameter, so a model mistake cannot cross producers.
- **People stay in the loop.** Stored records are reviewed by a person before they count.

## How the pieces fit

| Part | Path | What it is |
|---|---|---|
| Agent | `agent/` | The conversation engine, data tools, guardrail and records, on AgentCore Runtime (Python, Strands) |
| Data | `data/` | The `fx_data` package: producer, peer, regional and standards data, and the generators |
| API | `api/` | The REST API (TypeScript, Node.js): chat, write-back, review, analytics, "your record" |
| Web | `web/` | The Vue app: producer chat, "your record", reviewer and admin views |
| Infra | `infra/` | The CDK stack that deploys it all |

## What to read next

1. The [vision document](../requirements/vision.md) and the [technical environment](../requirements/technical-environment.md)
   for the why and the production context.
2. The [specs index](../specs/README.md): one spec per feature, each the implementation contract. The
   rules at the top of that file explain how specs, "shared contract" ownership and "Not decided" items work.
3. The [architecture decision records](../adr/): [0001](../adr/0001-architecture.md) (overall shape) and
   [0002](../adr/0002-agentcore-runtime-spike.md) (the AgentCore Runtime spike and its follow-up findings).
4. Then this package, in order: [Deploy](02-deploy.md) → [Interfaces](03-interfaces.md) →
   [Data](04-data.md) → [Stand-in → target mapping](05-stand-in-to-target.md) →
   [Known limitations and open decisions](06-known-limitations.md).
