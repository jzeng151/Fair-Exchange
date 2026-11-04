# Handoff package (#39)

For Fair Trade USA Digital Technology: everything needed to redeploy and run Fair Exchange in your
own account. Each document links to its source of truth (the specs, the generated schema, the CDK
outputs) rather than copying it, so it stays current as interfaces change (see
[CONTRIBUTING](../../CONTRIBUTING.md)).

Spec: [docs/specs/39-handoff.md](../specs/39-handoff.md).

## Read in this order

1. [Start here](01-start-here.md) — what Fair Exchange is, and what to read next.
2. [Deploy](02-deploy.md) — the single-command deploy, prerequisites, configuration, outputs, teardown.
3. [Interfaces](03-interfaces.md) — the record schema, the data-tool contracts, the agent request/
   action/event schemas, and the API routes with their roles.
4. [Data](04-data.md) — the synthetic data generator, the vocabulary mapping, the survey allowlist,
   the regional fact table, and how to replace each with your own data.
5. [Stand-in → target mapping](05-stand-in-to-target.md) — each sandbox stand-in and the production
   target that replaces it.
6. [Known limitations and open decisions](06-known-limitations.md) — what to know before production,
   and every decision the specs left open.

## Supporting documents

- [Tool contracts](tool-contracts.md) — the full input/output/guarantee contract for every data tool.
- [Sandbox deployment](sandbox-deployment.md) — how the sandbox was deployed, and the full-stack
  deployment checklist for #5.

## Keeping it current

A PR that changes an interface updates the matching handoff document in the same PR (the PR template
has the checkbox). Two CI checks guard this package:

- **Link check** (`check_links.py`): fails if a relative link in `docs/handoff/` or `docs/specs/`
  points to a missing file.
- **Open-decisions check** (`check_open_decisions.py`): fails if a spec has a "Not decided" section
  that the [open decisions list](06-known-limitations.md#open-decisions) does not reference.

The final proof is the timed clean redeploy (#40): the person running
it follows only these documents and records every step that was missing or wrong, which is fixed
before close.

### Wiring the checks into CI

Both checks are plain Python (no dependencies) and run from the repository root. A maintainer adds
this step to the `checks` job in `.github/workflows/ci.yml` (kept out of this PR because the push
token lacks `workflow` scope):

```yaml
      - name: Handoff docs checks
        run: |
          python docs/handoff/check_links.py
          python docs/handoff/check_open_decisions.py
```

Until then, run them locally before changing an interface.
