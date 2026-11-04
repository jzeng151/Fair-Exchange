/**
 * Small-cell suppression for the Analytics API (#29 spec). Pure: no AWS, no I/O.
 *
 * Takes the raw live counts for BOTH views at once (reviewed-only and include-pending) and
 * returns both views with the same cells hidden, so comparing the two responses reveals nothing:
 *
 *   1. Small cells: a count of 1 to 4 in either view is hidden. Pending rule: a pending-only
 *      count (include-pending minus reviewed) of 1 to 4 is hidden.
 *   2. A cell hidden in either view is hidden in both.
 *   3. Second cell: in each view, a breakdown with exactly one hidden cell also hides its
 *      next-smallest cell (by that view's counts).
 *   4. Repeat 2 and 3 until every breakdown has no hidden cells or at least two, in both views.
 *
 * Completed-vs-declined is passed in as an ordinary two-cell breakdown, so every rule applies to
 * it too. Nothing here returns a total. Seeded counts must never be passed in: they are not
 * suppressed and are never mixed with live counts.
 */

export const MIN_CELL = 5;

/** A hidden cell. Never a number. */
export const SUPPRESSED = Object.freeze({ suppressed: true as const });
export type Suppressed = typeof SUPPRESSED;
export type Cell = number | Suppressed;

/** Raw counts for one cell: reviewed records only, and reviewed plus pending. */
export interface ViewCounts {
  reviewed: number;
  all: number;
}

/** breakdown name -> cell key -> raw counts. */
export type CountTable = Record<string, Record<string, ViewCounts>>;

/** breakdown name -> cell key -> shown count or SUPPRESSED. */
export type SuppressedView = Record<string, Record<string, Cell>>;

export interface SuppressedViews {
  reviewed: SuppressedView;
  include_pending: SuppressedView;
}

const isSmall = (n: number) => n >= 1 && n < MIN_CELL;

function check(table: CountTable): void {
  for (const [b, cells] of Object.entries(table)) {
    for (const [c, { reviewed, all }] of Object.entries(cells)) {
      const ok = Number.isInteger(reviewed) && Number.isInteger(all) && reviewed >= 0 && all >= reviewed;
      if (!ok) throw new Error(`Invalid counts for ${b}/${c}: reviewed=${reviewed}, all=${all}`);
    }
  }
}

/**
 * The visible cell to hide alongside a single hidden one: the smallest by `count`, preferring a
 * non-zero cell (hiding a zero protects nothing). Ties break on the key so output is stable.
 */
function nextSmallest(
  cells: Record<string, ViewCounts>,
  hidden: Set<string>,
  count: (v: ViewCounts) => number,
): string | undefined {
  const visible = Object.keys(cells)
    .filter((k) => !hidden.has(k))
    .sort((a, b) => {
      const na = count(cells[a]!);
      const nb = count(cells[b]!);
      return Number(na === 0) - Number(nb === 0) || na - nb || (a < b ? -1 : a > b ? 1 : 0);
    });
  return visible[0];
}

/** The hidden cells of each breakdown. The same set applies to both views. */
export function hiddenCells(table: CountTable): Record<string, Set<string>> {
  check(table);
  const result: Record<string, Set<string>> = {};
  for (const [b, cells] of Object.entries(table)) {
    // Step 1 (both views), merged at once (step 2): hidden if hidden in either view.
    const hidden = new Set(
      Object.entries(cells)
        .filter(([, { reviewed, all }]) => isSmall(reviewed) || isSmall(all) || isSmall(all - reviewed))
        .map(([k]) => k),
    );
    // Steps 3 and 4: second-cell hiding in each view, merged, until no breakdown has exactly one.
    while (hidden.size === 1) {
      const fromReviewed = nextSmallest(cells, hidden, (v) => v.reviewed);
      const fromPending = nextSmallest(cells, hidden, (v) => v.all);
      if (fromReviewed === undefined && fromPending === undefined) break; // one-cell breakdown
      for (const k of [fromReviewed, fromPending]) if (k !== undefined) hidden.add(k);
    }
    result[b] = hidden;
  }
  return result;
}

/** Applies the #29 suppression rules to both views together. */
export function suppress(table: CountTable): SuppressedViews {
  const hidden = hiddenCells(table);
  const view = (count: (v: ViewCounts) => number): SuppressedView =>
    Object.fromEntries(
      Object.entries(table).map(([b, cells]) => [
        b,
        Object.fromEntries(
          Object.entries(cells).map(([k, v]) => [k, hidden[b]!.has(k) ? SUPPRESSED : count(v)]),
        ),
      ]),
    );
  return { reviewed: view((v) => v.reviewed), include_pending: view((v) => v.all) };
}
