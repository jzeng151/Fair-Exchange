# web/

Vue 3 + Vite (TypeScript). One app, two sides:

- `#/`: **Producer**, the chat with FEX (issue #30)
- `#/review`: **Fair Trade USA**, records to review (issue #31). The admin dashboard (#33) comes later.

```bash
npm ci
npm run dev      # http://localhost:5173
npm test         # Vitest
npm run build    # tests + type check + production build (what CI and the deploy run)
```

## What a producer sees

Start screen with three synthetic producers (🇨🇴 drought in **Spanish**, 🇲🇽 price drop, 🇨🇮 labor shortage), then FEX:
open question → follow-ups → editable playback → "looking things up" checklist → **answer as four tap-through cards**
(In short · What the data shows · What others tried, with trade-offs · Your summary) → save preview with consent → feedback.
Every insight and example shows its **source and APS/FPS clause** under "Where does this come from?". FEX never tells the
producer what to do and hands the decision back. An **English subtitles** switch shows English under every Spanish line.

## What a reviewer sees (`#/review`)

A list of records (filter: all, pending, reviewed, flagged, declined) and the selected record:
producer ID, saved time, source, consent, entity type, **language**, feedback, the **personal-information flag**,
the **summary** (original and English), the **challenge tags**, what FEX told the producer (with sources and clauses),
and the **agent's reasoning** (tool calls, in order). The reviewer approves, or corrects tags and summary, and the
record is marked **reviewed** with who and when. Corrections that would break the #6 rules are refused (no tags,
an unknown tag, a non-English record without an English summary). Declined records have nothing to review.
"Load demo records" adds synthetic records covering each state.

## Demo mode (until the chat API, #25)

- Replies are **scripted** from `src/data/scenarios.ts` (synthetic producers and numbers, **real** APS/FPS clause IDs).
- Saved and declined records are built with the **generated #6 schema types** (`src/lib/record.ts`) and kept in this
  browser only (`src/lib/demoStore.ts`). To connect the backend, replace `demoStore` with calls to #25/#26/#27; the record shape doesn't change.
- The reasoning trace is stored next to the record, keyed by record ID. In production it comes from AgentCore Observability.

## Tests (`npm test`)

- Records match the #6 schema: completed vs. declined, consent scope, English summary rule; a decline carries no narrative.
- Every clause the demo cites exists in `data/src/fx_data/clauses.json` (#9).
- Every Spanish line has an English version; Spanish and English UI copy have the same keys.
- Reviews (`src/lib/review.ts`): approve or correct, mark reviewed; never change producer, source or consent; refuse corrections that break the schema rules.
- Demo records: every state is present, every one is reviewable, clauses are real, each completed record has a trace.
- No directive wording ("you should", "debería", "recomendamos"…) anywhere in FEX's copy.

Design tokens: `src/styles/tokens.css` (FTUSA UI/UX spec v1.1). Accessibility target: WCAG 2.2 AA.
