#!/usr/bin/env python3
"""Smoke the six evaluator Lambdas against fixture conversations (spec [36](https://github.com/jzeng151/Fair-Exchange/issues/36)).

Usage:
    python eval_smoke.py --records-table TABLE --evidence-bucket BUCKET \
        --function ARN --function ARN ... [--region us-west-2]

Writes two fixture records into the eval records table (one completed conversation with a
shown insight, one declined with no narrative content) and one evidence capture into the eval
evidence bucket, then invokes every evaluator Lambda once per conversation, paced at one
request per second. Each response must carry the handler's evaluator id and a value; the
declined conversation scores tag_overlap 0.0 and scope_leak 0.0, and the completed one scores
directive_language 0.0 (its one shown claim is neutral, non-directive text).

Exit status 0 only when every invocation returned a well-formed, matching result.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.types import TypeSerializer

NOW = datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc).isoformat()
CONVERSATION_ID = "smoke-eval-001"
DECLINED_ID = "smoke-eval-002"

INSIGHT_TEXT = "Prices fell by twelve percent across the valley this season."
CITATION = {
    "source": "regional:coffee-price-feed",
    "standard_clause": "APS 3.2.1",
    "strength": "nearest",
}

COMPLETED_RECORD = {
    "status": "completed",
    "record_id": CONVERSATION_ID,
    "producer_id": "P-smoke-001",
    "created_at": NOW,
    "updated_at": NOW,
    "version": 1,
    "consent": {"scope": "internal", "recorded_at": NOW},
    "language": "en",
    "entity_type": "smallholder",
    "summary_original": "Prices dropped across the valley this season.",
    "tags": ["market and price"],
    "evidence": "full",
    "insights": [{"text": INSIGHT_TEXT, "citation": CITATION}],
}

DECLINED_RECORD = {
    "status": "declined",
    "record_id": DECLINED_ID,
    "producer_id": "P-smoke-002",
    "created_at": NOW,
    "updated_at": NOW,
    "version": 1,
    "consent": {"scope": "declined", "recorded_at": NOW},
}

EVIDENCE = {
    "conversation_id": CONVERSATION_ID,
    "final_step": "done",
    "tool_items": [
        {
            "tool": "regional_context",
            "source": "regional:coffee-price-feed",
            "data": {"note": "prices fell by twelve percent this season"},
        }
    ],
    "clauses": [],
    "claims": [{"kind": "insight", "text": INSIGHT_TEXT, "citation": CITATION}],
    "dropped": [],
}

# The declined conversation kept no narrative content — an empty capture is still stored so the
# evidence store always has the conversation's key (spec 36 never-mix: separate stack, disposable).
DECLINED_EVIDENCE = {
    "conversation_id": DECLINED_ID,
    "final_step": "declined",
    "tool_items": [],
    "clauses": [],
    "claims": [],
    "dropped": [],
}

REFERENCE = {
    "scenario_id": "smoke-eval-001",
    "reference_tags": ["market and price"],
    "forbidden": ["P-peer-999", "Goh-Djiboua", "cote-divoire-cocoa"],
}


def put_records(table_name: str, region: str) -> None:
    table = boto3.client("dynamodb", region_name=region)
    serializer = TypeSerializer()
    for record in (COMPLETED_RECORD, DECLINED_RECORD):
        table.put_item(
            TableName=table_name,
            Item={k: serializer.serialize(v) for k, v in record.items()},
        )


def invoke_all(function_arns: dict[str, str], region: str, session_id: str) -> list[dict]:
    lambda_client = boto3.client("lambda", region_name=region)
    payloads = []
    for evaluator_id, arn in function_arns.items():
        time.sleep(1.0)  # spec pacing: one request per second
        response = lambda_client.invoke(
            FunctionName=arn,
            Payload=json.dumps({"session_id": session_id, "reference": REFERENCE}).encode(),
        )
        body = json.loads(response["Payload"].read())
        payloads.append({"evaluator_id": evaluator_id, "arn": arn, "result": body})
    return payloads


def check(payloads: list[dict], session_id: str) -> list[str]:
    problems = []
    for entry in payloads:
        result = entry["result"]
        if not isinstance(result, dict):
            problems.append(f"{entry['evaluator_id']}: not a dict: {str(result)[:120]}")
            continue
        if result.get("evaluator_id") != entry["evaluator_id"]:
            problems.append(
                f"{entry['evaluator_id']}: id mismatch {result.get('evaluator_id')!r}")
        if "value" not in result:
            problems.append(
                f"{entry['evaluator_id']}: no value in {json.dumps(result)[:160]}")
        if result.get("session_id") not in (None, session_id):
            problems.append(
                f"{entry['evaluator_id']}: session_id {result.get('session_id')!r} != {session_id!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-table", required=True)
    parser.add_argument("--evidence-bucket", required=True)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--function", action="append", required=True,
                        metavar="EVALUATOR=FUNCTION_ARN",
                        help="repeat once per evaluator, e.g. --function tag_overlap=arn:...")
    args = parser.parse_args()

    function_arns = {}
    for spec in args.function:
        if "=" not in spec:
            parser.error(f"--function expects EVALUATOR=ARN, got {spec!r}")
        evaluator_id, arn = spec.split("=", 1)
        function_arns[evaluator_id] = arn

    problems: list[str] = []
    print(f"[1/4] Writing fixture records into {args.records_table}")
    put_records(args.records_table, args.region)
    print(f"[2/4] Writing the evidence captures into s3://{args.evidence_bucket}/")
    evidence = boto3.client("s3", region_name=args.region)
    for capture in (EVIDENCE, DECLINED_EVIDENCE):
        evidence.put_object(
            Bucket=args.evidence_bucket,
            Key=capture["conversation_id"],
            Body=json.dumps(capture).encode(),
            ContentType="application/json",
        )

    by_id: dict[str, dict] = {}
    for label, session_id in (("completed", CONVERSATION_ID), ("declined", DECLINED_ID)):
        print(f"[3/4] Invoking the six evaluators ({label} conversation)")
        payloads = invoke_all(function_arns, args.region, session_id)
        problems.extend(check(payloads, session_id))
        for entry in payloads:
            result = entry["result"]
            value = result.get("value") if isinstance(result, dict) else None
            print(f"    {entry['evaluator_id']:<22} value={value}  "
                  f"breakdown={json.dumps(result.get('breakdown')) if isinstance(result, dict) else ''}")
            if isinstance(result, dict) and session_id == DECLINED_ID:
                by_id[entry["evaluator_id"]] = result

    # Spec 36 sanity on a known pair: the declined record kept nothing shown, so it is clean.
    if by_id.get("tag_overlap", {}).get("value") not in (0.0, 0, None):
        problems.append(f"declined tag_overlap expected 0.0, got {by_id['tag_overlap'].get('value')}")
    if by_id.get("scope_leak", {}).get("value") not in (0.0, 0, None):
        problems.append(f"declined scope_leak expected 0.0, got {by_id['scope_leak'].get('value')}")

    if problems:
        print("SMOKE FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("[4/4] All six evaluators returned well-formed results for both conversations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
