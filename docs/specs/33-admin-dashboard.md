# Spec: Admin analytics dashboard (#33)

Status: approved for build, 2026-11-04. Should-have: start only once the must-haves are on track (decided 2026-11-04).

## Problem Statement

FTUSA admins need to see what the analytics API returns without reading JSON. The view must also preserve the API's privacy rules: hidden small groups, declines as counts only, and a clear label on seeded data.

## Solution

An admin route in the same Vue app that shows each breakdown from the Analytics API ([#29 spec](29-analytics-api.md)) as a simple chart or table. Hidden cells show "Hidden for privacy", and seeded demo data appears in its own labeled section.

## User Stories

1. As an FTUSA admin, I want each breakdown as a bar chart or table, so that I can read it at a glance.
2. As an FTUSA admin, I want hidden cells to read "Hidden for privacy" rather than disappear, so that I know data exists but is protected.
3. As an FTUSA admin, I want a toggle to include pending records, so that I can see recent activity (cells that would reveal small pending counts stay hidden).
4. As an FTUSA admin, I want seeded demo data shown in its own clearly labeled section, so that I do not mistake it for real activity.
5. As an FTUSA admin, I want the AI footprint shown, so that I can see model usage.

## Implementation Decisions

- **Placement.** Vue 3 with TypeScript, an admin route in the existing app, shown only to users with the `admin` role ([#11 spec](11-identity.md)).
- **Data.** Calls `GET /analytics`, using `include_pending` for the toggle. It displays only what the API returns and computes no totals of its own, so suppression cannot be undone in the browser.
- **Charts.** Horizontal bars for categorical counts, with value labels. Suppressed cells are drawn as a hatched bar labeled "Hidden for privacy" with no number. The label never states or implies a size, because cells hidden as a second cell or by the pending rule can hold 5 or more.
- **Seeded data.** The `seeded` section is shown separately under the heading "Seeded demo data", never combined with live counts.
- **Errors.** A 503 shows "Analytics are taking too long. Try again." with a retry button.

## Testing Decisions

- **Component tests (Vitest with Vue Test Utils)** with a mocked API response:
  - suppressed cells show "Hidden for privacy" and no number or size hint;
  - a hidden AI footprint shows "Hidden for privacy" for its totals and average;
  - no client-side totals are computed;
  - seeded and live sections are shown separately and never summed;
  - a 503 shows the retry message;
  - the toggle sends `include_pending`.

## Out of Scope

- Exports, drill-down, region maps
