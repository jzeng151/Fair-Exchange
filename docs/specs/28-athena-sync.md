# Spec: Athena sync and record table (#28)

Status: approved for build (record table and sync), 2026-11-04. Revised 2026-11-04 after review.

## Problem Statement

FTUSA's Journey 3 query joins conversation records to the producer's Premium, survey and certification data in Athena (the Redshift stand-in). Records live in DynamoDB and change after creation: producer consent changes, and reviewer corrections.

Three things can make Athena drift from the real record:
- several pieces of code writing to both DynamoDB and S3;
- a crawler guessing the table shape, so it is never reviewed;
- a replayed or out-of-order event writing an old version of a record, which could bring back narrative the producer has since declined.

## Solution

DynamoDB is the only place code writes records. A DynamoDB Streams consumer treats each event only as a signal that a record changed. It re-reads the record's current state from DynamoDB and writes that to one S3 object per record, or deletes the object if the record is gone. Old or replayed events therefore always converge on the current state.

A Glue table defined in CDK lets Athena query the objects. A resync command rebuilds S3 from DynamoDB if anything is ever missed.

## User Stories

1. As an FTUSA analyst, I want records queryable in Athena with current consent and review state, so that I can join them to Premium, survey and certification data.
2. As an FTUSA analyst, I want consent changes and reviewer corrections to appear in Athena without a manual export, so that queries reflect the current record.
3. As an FTUSA analyst, I want deleted records to disappear from Athena, so that they do not linger in analytics.
4. As a producer, I want narrative I declined never to reappear in Athena from an old event, so that my choice holds.
5. As an FTUSA analyst, I want the join query to run on Redshift too, so that it ports to Atlas.
6. As an FTUSA engineer, I want one command that rebuilds S3 from DynamoDB, so that any missed sync can be repaired.
7. As an FTUSA engineer, I want the Glue table in CDK, not discovered by a crawler, so that its shape is reviewed and deploys in one command.

## Implementation Decisions

- **Trigger.** A Python Lambda consumes the records table stream ([#26 spec](26-write-back.md)), with keys-only stream records.
- **Re-read, don't trust the event.**
  - For each changed `record_id`, the Lambda does a strongly consistent read of the current item.
  - If the item exists, it writes it as plain JSON (unmarshalled, not DynamoDB-typed) to a fixed key per record: a `records/` prefix plus `record_id`. This overwrites the previous object.
  - If the item no longer exists, it deletes the object.
- **Failures.**
  - The Lambda uses partial batch failure reporting and bisect on error.
  - Its on-failure destination is an S3 bucket, so failed batches are kept beyond the stream's 24-hour retention. Confirm in the #4 spike that the kept batch includes the record keys.
- **Resync command.** A script scans the records table, rewrites every object, and deletes objects whose record no longer exists. It is the repair path for anything the stream missed.
- **Bucket.** KMS-encrypted, public access blocked, separate from the web bucket.
- **Glue and Athena.**
  - A Glue database and records table are defined in CDK over the `records/` prefix with a JSON SerDe. Columns mirror the record, with structs and arrays for nested fields. No crawlers.
  - An Athena workgroup with its own results location is defined in CDK.
- **History.** Athena shows only the current version of each record. History lives inside the record ([#26 spec](26-write-back.md)). Athena lags DynamoDB by seconds.
- **Join query.**
  - The Journey 3 query joins records to the synthetic Premium, survey and certification tables on `producer_id`.
  - It selects scalar columns only (e.g., status, consent scope, review status, evidence, language, entity type, effective English summary), so it stays Redshift-compatible.
  - Tag-level analysis needs `UNNEST`, which Redshift does not support the same way. It is Athena-only and labeled as such.
  - The query ships as an Athena named query in CDK. The synthetic tables come from the data work (#7).

## Testing Decisions

- **Seam 2 (Lambda handler),** per the [specs README](README.md), with stream events and moto for DynamoDB and S3. Cases:
  - a changed record written as plain JSON;
  - an old event for a record that has since changed writing the current state, not the old one;
  - an event for a deleted record deleting the object;
  - a failure on one record reported as a batch item failure without blocking the rest.
- **Resync command** against moto: an orphaned object deleted and a missing object written.
- **Seam 3 (deployed smoke test):** after a scripted conversation, an Athena query returns the record with the right status and consent. After a consent change, it returns the new value.

## Out of Scope

- Synthetic Premium, survey and certification tables (#7)
- Analytics dashboards (later batch)

## Further Notes

### Not decided (do not build or assume)

- Whether records of conversations that are still open appear in Athena. The sync currently copies every record. Keep any filter for this in one place in the sync Lambda so it can be added without restructuring.
