"""Drive one full conversation through the LOCAL chat API (#101) and check every step.

    python3 scripts/e2e/local_conversation.py [--api http://127.0.0.1:3000] [--records DIR] [--producer ID]

Web client's view (#25 spec): POST /conversations, /messages {text}, /actions {action, args} (NDJSON streams)
and GET /conversations/{id}.
Behind it run the real chat API route logic and the real agent engine (see scripts/e2e/run_local.sh).
Exits non-zero, with the failing step, if anything is wrong. Standard library only.
Against the deployed API, pass --api <ApiUrl> and set FEX_DEMO_PASSCODE (the sign-in stand-in, #11).
"""
from __future__ import annotations  # run under the system python3, which may be 3.9 (PEP 604 unions in annotations)

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

SPANISH = ["La lluvia ha bajado mucho y la cosecha de café cayó este año.", "Empezó hace dos temporadas.",
           "Es grave, perdimos casi la mitad.", "Probamos con abono, pero no alcanzó."]


class Client:
    def __init__(self, api: str, producer: str) -> None:
        self.api, self.producer = api.rstrip("/"), producer

    def _request(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(f"{self.api}{path}", method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"content-type": "application/json", "x-demo-producer-id": self.producer})
        if os.environ.get("FEX_DEMO_PASSCODE"):
            req.add_header("x-demo-passcode", os.environ["FEX_DEMO_PASSCODE"])
        return urllib.request.urlopen(req, timeout=300)

    def turn(self, path: str, body: dict) -> list[dict]:
        with self._request("POST", path, body) as res:
            assert "ndjson" in res.headers.get("content-type", ""), res.headers.get("content-type")
            return [json.loads(line) for line in res.read().decode().splitlines() if line.strip()]

    def get(self, path: str) -> dict:
        with self._request("GET", path) as res:
            return json.loads(res.read())


def say(events: list[dict]) -> str:
    return "".join(e.get("text", "") for e in events if e["type"] == "text")


def check(condition: bool, step: str) -> None:
    if not condition:
        print(f"FAILED at: {step}")
        sys.exit(1)
    print(f"  ok  {step}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:3000")
    ap.add_argument("--records", default=None, help="FEX_LOCAL_RECORDS_DIR the agent writes to")
    ap.add_argument("--producer", default="SYN-001", help="a Cauca coffee producer")
    args = ap.parse_args()
    c = Client(args.api, args.producer)
    started = time.time()

    first = c.turn("/conversations", {})
    cid = next(e["conversationId"] for e in first if e["type"] == "conversation")
    print(f"conversation {cid}\nFEX: {say(first)}")
    check(any(e.get("step") == "intake" for e in first) and first[-1]["type"] == "done", "start: open question, intake")

    events = []
    for text in SPANISH:
        print(f"PRODUCER: {text}")
        events = c.turn(f"/conversations/{cid}/messages", {"text": text})
        print(f"FEX: {say(events)}")
    check(any(e.get("step") == "playback" for e in events), "intake follow-ups, then playback")
    check(any(e.get("language") == "es" for e in events), "language identified as Spanish")

    answer = c.turn(f"/conversations/{cid}/actions", {"action": "confirm_playback", "args": {}})
    claims = [e for e in answer if e["type"] == "claim"]
    for e in claims:
        cit = e["claim"]["citation"]
        print(f"  [{e['section']}] {e['claim']['text'][:90]}  — {cit['source'][:50]} · {cit['standard_clause']}")
    check({e["section"] for e in claims} == {"insights", "peer_examples"}, "checked claims streamed: insights and peers")
    check(any(e["type"] == "answer" for e in answer) and any(e.get("step") == "consent" for e in answer),
          "answer complete, consent asked")

    consent = c.turn(f"/conversations/{cid}/actions", {"action": "set_consent", "args": {"scope": "internal"}})
    saved = [e for e in consent if e["type"] == "record_saved"]
    check(saved and saved[0]["version"] == 1 and saved[0]["status"] == "completed", "consent saves the record (v1)")
    feedback = c.turn(f"/conversations/{cid}/actions", {"action": "set_feedback", "args": {"value": "yes"}})
    check(any(e["type"] == "record_saved" and e["version"] == 2 for e in feedback), "feedback updates it (v2)")

    resumed = c.get(f"/conversations/{cid}")
    check(resumed.get("step") == "feedback" and resumed.get("answer"), "GET returns step and answer (resume)")
    end = c.turn(f"/conversations/{cid}/actions", {"action": "end", "args": {}})
    check(any(e.get("step") == "closed" for e in end), "end closes the conversation")

    if args.records:
        record = json.loads((Path(args.records) / f"{cid}.json").read_text(encoding="utf-8"))
        print(f"record: status={record['status']} language={record['language']} tags={record['tags']} "
              f"evidence={record['evidence']} feedback={record['feedback']} version={record['version']}")
        check(record["status"] == "completed" and record["closed_at"] and record["version"] == 3,
              "record saved: completed, closed, version 3")
    print(f"PASSED: full conversation in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
