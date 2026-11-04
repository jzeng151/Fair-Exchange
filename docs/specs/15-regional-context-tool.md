# Spec: Regional-context tool (#15)

Status: approved for build, 2026-11-04. Merged code differs from this spec (#53). Decided 2026-11-04: the spec wins, and the code changes to match in the retro review.

## Problem Statement

"What the data shows" has to be about this producer's region, crop and challenge, not a generic statement. The location must come from the session, never from the model or the producer's text, or a producer could steer the tool to another producer's area.

## Solution

A data tool that reads the regional fact table ([#8 spec](08-regional-fact-table.md)) and returns the facts matching the producer's profile location and crop and the confirmed challenge tags.

## User Stories

1. As a producer, I want facts about my own region and crop, so that the evidence applies to me.
2. As a producer, I want facts relevant to the challenge I confirmed, so that the answer is about my problem.
3. As a producer, I want region-level facts marked differently from country-level ones, so that I know how closely they apply.
4. As a producer in a country the table does not cover, I want FEX to say it lacks data rather than guess, so that I am not misled.
5. As an FTUSA engineer, I want the location taken only from the profile, so that the tool cannot be steered to another area.

## Implementation Decisions

- **Contract.** The shared data tool contract ([#17 spec](17-standards-grounding.md)).
- **Inputs, all from conversation state:**
  - profile country and region (`admin1`), which never come from corrections ([#13 spec](13-conversation-steps.md));
  - profile crops (normalized, [#14 spec](14-producer-record-tool.md));
  - the confirmed tags.
- **Matching.** It returns rows whose tags overlap the confirmed tags, and:
  - for **region-level rows**, whose `country` and `admin1` match the profile. Strength is `exact`.
  - for **country-level rows**, whose `country` matches. Strength is `nearest`.
  - for **global rows** (e.g., benchmark prices). Strength is `limited`.
  - Rows with a crop must match one of the profile crops. Rows without a crop always qualify.
- **Limit.** At most 8 items: region rows, then country, then global.
- **Item.** `source` is the fact table's source label. `text` states the value, unit, comparison and period. `data` holds the row.
- **No coverage.** Returns an empty list, which leads to the limited-evidence path.

## Testing Decisions

- **Seam 1 (agent entrypoint) with fixture rows:**
  - region match marked `exact`;
  - country match marked `nearest`;
  - global price row marked `limited`;
  - crop filtering;
  - tag filtering;
  - an uncovered country returning an empty list;
  - a disputed location in the conversation not changing the rows returned;
  - sources reaching session evidence.

## Out of Scope

- Searching neighboring regions or similar crops when nothing matches. This was considered and not chosen on 2026-11-04.
