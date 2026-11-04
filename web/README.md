# web/

Vue 3 + Vite (TypeScript). The producer chat with FEX (issue #30). The Fair Trade USA reviewer view (#31) and dashboard (#33) come later.

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

## Demo mode (until the chat API, #25)

- Replies are **scripted** from `src/data/scenarios.ts` (synthetic producers and numbers, **real** APS/FPS clause IDs).
- Saved and declined records are built with the **generated #6 schema types** (`src/lib/record.ts`) and kept in this
  browser only (`src/lib/demoStore.ts`). To connect the backend, replace `demoStore` with calls to #25/#26; the record shape doesn't change.

## Tests (`npm test`)

- Records match the #6 schema: completed vs. declined, consent scope, English summary rule; a decline carries no narrative.
- Every clause the demo cites exists in `data/src/fx_data/clauses.json` (#9).
- Every Spanish line has an English version; Spanish and English UI copy have the same keys.
- No directive wording ("you should", "debería", "recomendamos"…) anywhere in FEX's copy.

Design tokens: `src/styles/tokens.css` (FTUSA UI/UX spec v1.1). Accessibility target: WCAG 2.2 AA.
