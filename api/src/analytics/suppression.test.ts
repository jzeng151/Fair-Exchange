import { describe, expect, it } from 'vitest';
import { MIN_CELL, SUPPRESSED, suppress, type CountTable, type SuppressedView } from './suppression.js';

const hidden = (view: SuppressedView, breakdown: string): string[] =>
  Object.entries(view[breakdown] ?? {})
    .filter(([, v]) => typeof v !== 'number')
    .map(([k]) => k)
    .sort();

/** Same counts in both views: everything reviewed. */
const reviewedOnly = (cells: Record<string, number>) =>
  Object.fromEntries(Object.entries(cells).map(([k, n]) => [k, { reviewed: n, all: n }]));

describe('small cells', () => {
  it('hides 1 to 4 and shows 0 and 5 or more', () => {
    const { reviewed } = suppress({
      language: reviewedOnly({ en: 0, es: 5, fr: 1, pt: 4, de: 9 }),
    });
    expect(reviewed.language).toEqual({ en: 0, es: 5, fr: SUPPRESSED, pt: SUPPRESSED, de: 9 });
    expect(MIN_CELL).toBe(5);
  });

  it('returns a hidden cell as {"suppressed": true}, never a number', () => {
    const { reviewed, include_pending } = suppress({ language: reviewedOnly({ en: 3, es: 7, pt: 8 }) });
    expect(reviewed.language!.en).toEqual({ suppressed: true });
    expect(include_pending.language!.en).toEqual({ suppressed: true });
  });
});

describe('second cell', () => {
  it('hides the next-smallest cell when a breakdown has exactly one hidden cell', () => {
    const { reviewed } = suppress({ language: reviewedOnly({ en: 2, es: 30, fr: 6, pt: 9 }) });
    expect(hidden(reviewed, 'language')).toEqual(['en', 'fr']);
    expect(reviewed.language!.es).toBe(30);
    expect(reviewed.language!.pt).toBe(9);
  });

  it('prefers a non-zero cell as the second hidden cell', () => {
    const { reviewed } = suppress({ language: reviewedOnly({ en: 2, es: 30, fr: 0 }) });
    expect(hidden(reviewed, 'language')).toEqual(['en', 'es']);
  });

  it('leaves a breakdown with two hidden cells as it is', () => {
    const { reviewed } = suppress({ language: reviewedOnly({ en: 2, es: 3, fr: 6 }) });
    expect(hidden(reviewed, 'language')).toEqual(['en', 'es']);
    expect(reviewed.language!.fr).toBe(6);
  });
});

describe('pending-only rule', () => {
  it('hides a cell whose pending-only count is 1 to 4, in both views', () => {
    const { reviewed, include_pending } = suppress({
      language: { en: { reviewed: 10, all: 12 }, es: { reviewed: 20, all: 20 }, fr: { reviewed: 30, all: 40 } },
    });
    // en: pending-only 2 -> hidden; second cell: next smallest (es in both views).
    expect(hidden(reviewed, 'language')).toEqual(['en', 'es']);
    expect(hidden(include_pending, 'language')).toEqual(['en', 'es']);
    expect(reviewed.language!.fr).toBe(30);
    expect(include_pending.language!.fr).toBe(40);
  });

  it('hides completed and declined in both views when either has a pending-only difference of 1 to 4', () => {
    for (const participation of [
      { completed: { reviewed: 20, all: 22 }, declined: { reviewed: 10, all: 10 } },
      { completed: { reviewed: 20, all: 20 }, declined: { reviewed: 10, all: 13 } },
    ]) {
      const { reviewed, include_pending } = suppress({ participation });
      expect(hidden(reviewed, 'participation')).toEqual(['completed', 'declined']);
      expect(hidden(include_pending, 'participation')).toEqual(['completed', 'declined']);
    }
  });
});

describe('both views together', () => {
  it('reconstruction case: 1 completed and 5 declined, all pending: both hidden in both views', () => {
    const { reviewed, include_pending } = suppress({
      participation: { completed: { reviewed: 0, all: 1 }, declined: { reviewed: 0, all: 5 } },
    });
    expect(reviewed.participation).toEqual({ completed: SUPPRESSED, declined: SUPPRESSED });
    expect(include_pending.participation).toEqual({ completed: SUPPRESSED, declined: SUPPRESSED });
  });

  it('reconstruction case: reviewed A=1, B=5, five pending added to A: A and B hidden in both views', () => {
    const { reviewed, include_pending } = suppress({
      tag: { A: { reviewed: 1, all: 6 }, B: { reviewed: 5, all: 5 } },
    });
    expect(reviewed.tag).toEqual({ A: SUPPRESSED, B: SUPPRESSED });
    expect(include_pending.tag).toEqual({ A: SUPPRESSED, B: SUPPRESSED });
  });

  it('hides in both views the second cell chosen in either view', () => {
    // Hidden: x (small in reviewed). Next-smallest differs: y in reviewed, z in include-pending.
    const { reviewed, include_pending } = suppress({
      tag: {
        x: { reviewed: 2, all: 10 },
        y: { reviewed: 6, all: 50 },
        z: { reviewed: 40, all: 45 },
        w: { reviewed: 60, all: 60 },
      },
    });
    expect(hidden(reviewed, 'tag')).toEqual(['x', 'y', 'z']);
    expect(hidden(include_pending, 'tag')).toEqual(['x', 'y', 'z']);
  });

  it('never suppresses a breakdown in only one view', () => {
    // es: 3 pending only, so it is hidden in the include-pending view; the reviewed view must hide it too.
    const { reviewed, include_pending } = suppress({
      language: { en: { reviewed: 10, all: 10 }, es: { reviewed: 0, all: 3 }, fr: { reviewed: 7, all: 7 } },
    });
    expect(hidden(reviewed, 'language')).toEqual(hidden(include_pending, 'language'));
    expect(hidden(reviewed, 'language')).toEqual(['es', 'fr']);
  });
});

describe('input checks', () => {
  it('rejects a reviewed count above the include-pending count', () => {
    expect(() => suppress({ tag: { A: { reviewed: 6, all: 5 } } })).toThrow();
  });
  it('rejects negative or fractional counts', () => {
    expect(() => suppress({ tag: { A: { reviewed: -1, all: 5 } } })).toThrow();
    expect(() => suppress({ tag: { A: { reviewed: 1.5, all: 5 } } })).toThrow();
  });
});

/** Small deterministic PRNG so failures reproduce. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randomTable(rand: () => number): CountTable {
  const table: CountTable = {};
  const breakdowns = 1 + Math.floor(rand() * 5);
  for (let b = 0; b < breakdowns; b++) {
    const cells: CountTable[string] = {};
    const n = 1 + Math.floor(rand() * 6);
    for (let c = 0; c < n; c++) {
      // Skew towards small numbers so suppression triggers often.
      const reviewed = rand() < 0.3 ? Math.floor(rand() * 6) : Math.floor(rand() * 40);
      const pending = rand() < 0.4 ? 0 : rand() < 0.5 ? Math.floor(rand() * 6) : Math.floor(rand() * 30);
      if (reviewed + pending === 0) continue;
      cells[`c${c}`] = { reviewed, all: reviewed + pending };
    }
    table[`b${b}`] = cells;
  }
  return table;
}

describe('properties over random count tables', () => {
  const RUNS = 3000;

  it('no breakdown has exactly one hidden cell in either view (unless it has only one cell)', () => {
    const rand = rng(29);
    for (let i = 0; i < RUNS; i++) {
      const table = randomTable(rand);
      const out = suppress(table);
      for (const view of [out.reviewed, out.include_pending]) {
        for (const b of Object.keys(table)) {
          const cells = Object.keys(table[b]!).length;
          const h = hidden(view, b).length;
          if (cells > 1) expect(h === 0 || h >= 2, JSON.stringify(table[b])).toBe(true);
        }
      }
    }
  });

  it('a cell hidden in one view is hidden in the other', () => {
    const rand = rng(11);
    for (let i = 0; i < RUNS; i++) {
      const table = randomTable(rand);
      const out = suppress(table);
      for (const b of Object.keys(table)) {
        expect(hidden(out.reviewed, b), JSON.stringify(table[b])).toEqual(hidden(out.include_pending, b));
      }
    }
  });

  it('every shown cell is the true count, never 1 to 4, with no pending-only difference of 1 to 4', () => {
    const rand = rng(37);
    for (let i = 0; i < RUNS; i++) {
      const table = randomTable(rand);
      const out = suppress(table);
      for (const [b, cells] of Object.entries(table)) {
        expect(Object.keys(out.reviewed[b]!).sort()).toEqual(Object.keys(cells).sort());
        for (const [c, { reviewed, all }] of Object.entries(cells)) {
          const r = out.reviewed[b]![c];
          const a = out.include_pending[b]![c];
          if (typeof r === 'number') {
            expect(r).toBe(reviewed);
            expect(a).toBe(all);
            for (const n of [reviewed, all, all - reviewed]) expect(n === 0 || n >= MIN_CELL).toBe(true);
          } else {
            expect(r).toEqual(SUPPRESSED);
            expect(a).toEqual(SUPPRESSED);
          }
        }
      }
    }
  });
});
