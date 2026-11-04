# sync

Copies conversation records from the DynamoDB records table to S3, where Athena queries them. Spec: [28](../docs/specs/28-athena-sync.md).

DynamoDB is the only place code writes records. This package only reads from it.

## How it works

- `handler.py`: the Lambda for the table's stream (keys-only). An event is only a signal that a record changed. For each changed `record_id` it re-reads the current item (strongly consistent) and calls `sync_record`.
- `sync.py`: `sync_record` publishes the record, or deletes the object if the record is gone.
- `publish.py`: the only code that writes to S3. It stores the record's `version` in the object metadata and writes only if the object holds an older version. It uses an S3 conditional write (`If-Match` on the ETag it read, or `If-None-Match: *`). If another writer wins, it re-reads the record and the object and tries again.
- `resync.py`: rebuilds S3 from DynamoDB. It scans for record IDs only, re-reads each one, and deletes objects whose record no longer exists.
- `publish.should_publish` is the one place to filter which records reach Athena. Whether open conversations appear is not decided, so it currently copies every record.

Objects live at `records/<record_id>.json` as plain JSON. Records need an integer `version` (added by the write-back work, spec 26). A record without one is reported as a batch item failure.

## Develop

```
uv sync
uv run pytest
```

Tests use moto for DynamoDB and S3 and drive the Lambda with stream events.

## Resync

```
RECORDS_TABLE=<table> SYNC_BUCKET=<records bucket> uv run python -m fex_sync.resync
```

The bucket name is the `RecordsBucketName` output of the `FairExchangeAthenaSync` stack.

## Deploy

The stack is `infra/lib/athena-sync-stack.ts`. It needs the records table name and stream ARN (spec 26) and a code zip in S3:

```
cd sync && uv pip install -q --target build --python-platform x86_64-manylinux2014 --python-version 3.12 --only-binary=:all: .
cd build && zip -qr ../sync.zip . && cd ..
# upload sync.zip under a new key per build, then:
cd ../infra && npx cdk synth FairExchangeAthenaSync \
  -c recordsTableName=... -c recordsTableStreamArn=... -c syncCodeBucket=... -c syncCodeKey=...
```

Use a new S3 key for each build: CloudFormation does not notice changed code under the same key.
