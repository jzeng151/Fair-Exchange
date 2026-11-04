"""Drive one scripted conversation against the deployed FEX runtime directly (no chat API), as the API would.

    cd agent && uv run python ../scripts/e2e/runtime_conversation.py --runtime-arn <AgentRuntimeArn> \
        [--producer <producer id>] [--consent internal|declined] [--marker <sentence to search logs for>]

It sends start, the intake messages, confirm_playback, set_consent and set_feedback, prints each turn's events,
and checks the step order. Uses real models (a few cents per run). The conversation ID is fresh per run and is
also the AgentCore session ID, as in api/src/core/agent.ts. Sample producer IDs are anonymized sample data.
"""
import argparse
import json
import sys
import time
import uuid

import boto3

MESSAGES = [
    "Rainfall has dropped for two seasons and our coffee harvest fell by almost half.",
    "It started about two years ago.",
    "It is serious: members are earning much less.",
    "We tried planting shade trees, but they are still small.",
]


def events(client, runtime_arn: str, request: dict) -> list[dict]:
    response = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn, runtimeSessionId=request["conversationId"], contentType="application/json",
        accept="text/event-stream", payload=json.dumps(request).encode())
    body = response["response"].read().decode()
    out = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if line.startswith("{"):
            out.append(json.loads(line))
    return out


def summary(turn: list[dict]) -> str:
    parts = []
    for e in turn:
        if e.get("type") == "text":
            continue
        if e.get("type") == "claim":
            parts.append(f"claim[{e['section']}] {e['claim']['citation']['source'][:40]} | {e['claim']['citation']['standard_clause']}")
        elif e.get("type") in ("step", "actions", "answer", "error", "done"):
            parts.append(json.dumps({k: v for k, v in e.items() if k in ("type", "step", "allowed", "evidence", "code", "message")}))
    text = "".join(e["text"] for e in turn if e.get("type") == "text")
    return (f"  text: {text[:300]}\n" if text else "") + "\n".join("  " + p for p in parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-arn", required=True)
    ap.add_argument("--producer", default=None, help="sample producer ID (default: the first Cauca producer)")
    ap.add_argument("--consent", default="internal", choices=["internal", "internal_and_outward", "declined"])
    ap.add_argument("--marker", default=None, help="sentence appended to the first message, to search logs for")
    ap.add_argument("--region", default="us-west-2")
    args = ap.parse_args()
    if args.producer is None:
        from fx_data.peers import ProducerProfiles
        args.producer = next(pid for pid, p in ProducerProfiles.load()._profiles.items() if p["region"] == "Cauca")
    client = boto3.client("bedrock-agentcore", region_name=args.region)
    conversation = f"e2e-{uuid.uuid4()}"
    base = {"producerId": args.producer, "conversationId": conversation}
    first = MESSAGES[0] + (f" {args.marker}" if args.marker else "")
    script = [{"kind": "start"}] + [{"kind": "message", "text": t} for t in [first, *MESSAGES[1:]]]
    steps_seen: list[str] = []
    print(f"conversation {conversation}  producer {args.producer}")
    started = time.time()

    def send(extra: dict) -> list[dict]:
        t0 = time.time()
        turn = events(client, args.runtime_arn, {**base, **extra})
        steps_seen.extend(e["step"] for e in turn if e.get("type") == "step")
        print(f"> {extra.get('kind')} {extra.get('action', {}).get('name', '')} ({time.time() - t0:.1f}s)")
        print(summary(turn))
        return turn

    for request in script:
        turn = send(request)
        if steps_seen and steps_seen[-1] == "playback":
            break
    send({"kind": "action", "action": {"name": "confirm_playback", "args": {}}})
    send({"kind": "action", "action": {"name": "set_consent", "args": {"scope": args.consent}}})
    if args.consent != "declined":
        send({"kind": "action", "action": {"name": "set_feedback", "args": {"value": "yes"}}})
    order = [s for i, s in enumerate(steps_seen) if i == 0 or s != steps_seen[i - 1]]
    print(f"steps: {' -> '.join(order)}  ({time.time() - started:.0f}s total)")
    expected = ["intake", "playback", "respond", "consent"] + ([] if args.consent == "declined" else ["feedback"])
    ok = all(s in order for s in expected)
    print("PASS" if ok else f"FAIL: expected steps {expected}")
    print(f"record_id (= conversation ID): {conversation}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
