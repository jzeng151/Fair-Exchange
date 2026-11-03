# web/

Vue 3 + Vite (TypeScript). Two sides, one app:

- **Producer:** the FEX chat. Simple, phone-first, bilingual (Spanish/English). Answers come as short tap-through cards, sources behind "Where does this come from?", consent before saving. Issues #30, #32.
- **Fair Trade USA:** records to review (#31) and the dashboard: usage, challenge trends, issues needing attention, AI footprint (#33).

Design tokens are in `src/styles/tokens.css` (FTUSA UI/UX spec v1.1). Accessibility target: WCAG 2.2 AA.

```bash
npm install && npm run dev
```
