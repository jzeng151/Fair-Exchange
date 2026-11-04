"""Upload the seeded dashboard records (issue #37) to the records bucket, replacing the previous set.

    cd agent && uv run python scripts/load_seeded_records.py --bucket <records bucket> [--profile ftusa]
    cd agent && uv run python scripts/load_seeded_records.py --dry-run    # validate only, no AWS calls

Every record is validated with the record models first; if any is invalid, nothing is written.
Writes only under records-seeded/ (never DynamoDB). See fex/seeded.py.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fex.seeded import SEEDED_PREFIX, upload_seeded_records, validated_seeded_records  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", help="The records bucket")
    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--dry-run", action="store_true", help="Validate the set without uploading")
    args = parser.parse_args()
    if args.dry_run:
        print(f"{len(validated_seeded_records())} seeded records are valid")
        return
    if not args.bucket:
        parser.error("--bucket is required unless --dry-run")
    import boto3

    s3 = boto3.Session(profile_name=args.profile, region_name=args.region).client("s3")
    result = upload_seeded_records(s3, args.bucket)
    print(f"wrote {result.written} and deleted {result.deleted} objects under s3://{args.bucket}/{SEEDED_PREFIX}")


if __name__ == "__main__":
    main()
