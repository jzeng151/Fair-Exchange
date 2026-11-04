# Contributing

Read [`docs/requirements/vision.md`](docs/requirements/vision.md) and [`docs/requirements/technical-environment.md`](docs/requirements/technical-environment.md) before picking up work. They define the scope. Anything not listed under "Features In Scope" needs an issue and an OK from the repo owner before you build it.

## Issues

- Every change starts from an issue. Use the Feature, Bug or Spike template. Use the Question template when you need an answer from the team or FTUSA.
- Before you start an issue, check [`docs/specs/`](docs/specs/) for its spec. Each spec's title line names its issue, for example `# Spec: Chat endpoint (#25)`, so `grep -l '(#25)' docs/specs/*.md` finds it. If a spec exists, build what it says and follow the rules in [`docs/specs/README.md`](docs/specs/README.md).
- Leave issues unassigned when you open them. The repo owner assigns owners.
- Labels: one `type:`, one or more `area:`, one `priority:` (matches the vision doc's MoSCoW column), plus any `concern:` that applies.

## Branches

Name branches `type/short-desc`, where `type` is one of `feature`, `bug`, `docs`, `chore`, `spike`.

```
feature/regional-context-tool
bug/verifier-misses-fps-clauses
spike/agentcore-hello-world
```

Never push to `main`. All changes land through a pull request.

## Pull requests

- Keep PRs small: one issue per PR, ideally under 400 changed lines excluding generated files and data.
- Link the issue in the PR body (`Closes #12`).
- One approval is required before merge.
- If the PR touches anything with a `concern:` label, the reviewer adds the sign-off line from the PR template.
- Squash-merge only. The PR title becomes the commit message on `main`, so write it as one.
- Delete the branch after merge.

## Definition of Done

A PR is done when:

- [ ] Tests pass locally and in CI.
- [ ] The issue's acceptance criteria are met, and the PR description says how you checked each one.
- [ ] If you changed an interface (record schema, tool contract, API route, CDK output, deploy step), `docs/handoff/` is updated in the same PR.

## Repo conventions

- **Folders:** `agent/` (Python), `data/` (Python), `eval/` (Python), `api/` (TypeScript Lambdas), `web/` (Vue 3 + Vite), `infra/` (CDK, TypeScript), `docs/{requirements,adr,handoff,specs}`. Create a folder in the PR that adds its first real feature, not before.
- **One schema source:** the Pydantic models are the source of truth. JSON Schema and the TypeScript types are generated from them. Do not hand-edit generated files.
- **Scope enforcement:** agent tools use `@tool(context=True)` and read `producer_id` from `tool_context.invocation_state`. Never expose `producer_id` or location as a parameter the model can set.
- **PII:** flag it, never redact it.

## Commit and PR text

Do not add AI attribution anywhere in git-visible text. That means no `Co-Authored-By` lines for AI tools, no "Generated with ..." footers, and no mention of AI assistants in commit messages, PR titles or PR descriptions.

## Keeping `main` green

- **Merge `main` into your branch right before merging**, and let CI pass on that. Two PRs that each pass on their own can still break `main` together.
- **Changed `agent/src/fex/models.py` or `conversation/contract.py`?** Run `cd agent && uv run python scripts/generate_types.py` after merging `main`, and commit the result. CI's "Generated files are up to date" step fails otherwise.
- **New package with tests?** Add a CI step with its `working-directory`. The "Repo guard" step (`scripts/ci/check_repo.py`) fails if a package's tests aren't run, if a JSON file has a duplicate key, or if an iCloud-style duplicate (`name 2.py`) is committed.
- **If `main` fails CI**, a "main is failing CI" issue is opened automatically. Fix forward before merging anything else.
