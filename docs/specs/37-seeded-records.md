# Spec: Seeded conversation records for the dashboard (#37)

Status: approved for build, 2026-11-04. Should-have: start only once the must-haves are on track (decided 2026-11-04).

## Problem Statement

A few demo conversations will not clear the analytics rule that hides any group under 5, so the dashboard would show nothing. Seeded records must fill it without polluting real records, the reviewer queue, or tag-accuracy measurement.

## Solution

A generator in the data package produces a fixed set of synthetic conversation records that validate against the record schema. It writes them only to a separate S3 prefix with its own Glue table. Analytics reads them alongside live records and labels the result. They never enter DynamoDB, the reviewer view or evals.

## User Stories

1. As an FTUSA admin, I want the dashboard's seeded section to show meaningful breakdowns during the demo, so that the analytics feature can be evaluated.
2. As an FTUSA reviewer, I want seeded records never in my review list, so that I review only real conversations.
3. As an FTUSA engineer, I want seeded records kept apart from live records, so that they cannot affect tag accuracy or the Journey 3 join.
4. As an FTUSA engineer, I want the seeded set generated deterministically, so that the dashboard looks the same on every deploy.

## Implementation Decisions

- **Generator.** A Python generator in the data package with a fixed random seed. It produces about 200 records across:
  - the 11 tags;
  - `en` and `es`;
  - the entity types and priority countries' synthetic producers (#7);
  - all consent scopes, including declines;
  - feedback values;
  - both evidence markers;
  - reviewed and pending status;
  - plausible `ai_usage`.

  Producer IDs come from the producer table ([#14 spec](14-producer-record-tool.md)).
- **Validation.** Every record validates with the record models before it is written.
- **Storage.** Plain JSON objects under a `records-seeded/` prefix in the records bucket, with a separate Glue table that has the same columns as the live records table ([#28 spec](28-athena-sync.md)). They are never written to DynamoDB.
- **Use.** Only the Analytics API queries the seeded table, and it returns seeded counts as a separate series, never mixed into live counts ([#29 spec](29-analytics-api.md)). The Journey 3 join query, the reviewer API and evals use live records only.
- **Loading.** A deploy step uploads the generated set. Re-running replaces it.

## Testing Decisions

- **Generator tests (public function):**
  - the same seed gives the same output;
  - every record passes `parse_record`;
  - every tag, language and granted consent scope (`internal`, `internal_and_outward`) has at least 5 completed records, and there are at least 5 declined records;
  - declined records have no narrative.

## Out of Scope

- Seeding DynamoDB or the reviewer queue

## Further Notes

### Decisions made while writing this spec

- Seeded records live only in S3 under their own prefix and Glue table, not in the live records table or the record schema.
