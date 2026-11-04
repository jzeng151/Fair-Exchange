"""The enablement-tone judge (spec [36](https://github.com/jzeng151/Fair-Exchange/issues/36)).

A Bedrock large model scores the shown answer on the #17 rubric: 1 = dismissive or clinical,
3 = neutral, 5 = collaborative and options-forward. AWS-only: boto3 `Converse`, `us-west-2`.
The judge model config comes from the eval stack (env `EVAL_JUDGE_MODEL_ID`, default the
app's `small`/`large` Bedrock model id); a callable seam keeps unit tests hermetic.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

RUBRIC = """You are scoring one answer a Fair Trade premium-savings agent gave to a producer.

Rubric (1-5):
1 - dismissive or clinical; treats the producer as a case file
3 - neutral and polite but flat
5 - collaborative, options-forward, gives the producer agency and next steps

Score ONLY the enablement tone: warmth, agency, forward motion. Ignore factual accuracy,
grammar and formatting. Answer with JSON: {"score": <1..5>, "rationale": "<one sentence>"}."""

_SCORE_RE = re.compile(r"\b([1-5])\b")


@dataclass
class BedrockToneJudge:
    """The judge model on Bedrock (the app's large model unless overridden)."""

    model_id: str
    region: str = "us-west-2"
    client: Any = None  # pluggable for tests; a boto3 bedrock-runtime client by default

    @classmethod
    def from_env(cls, region: str = "us-west-2", default_model_id: str = "") -> "BedrockToneJudge":
        model_id = os.environ.get("EVAL_JUDGE_MODEL_ID") or default_model_id
        if not model_id:
            raise AssertionError(
                "the judge model id comes from EVAL_JUDGE_MODEL_ID or the stack's model config")
        return cls(model_id=model_id, region=region)

    def score(self, text: str) -> tuple[int, str]:
        if self.client is None:
            import boto3  # lazy: keeps the package importable without an AWS session
            self.client = boto3.client("bedrock-runtime", region_name=self.region)
        body = {
            "messages": [{"role": "user", "content": [{"text": f"{RUBRIC}\n\nAnswer:\n{text}"}]}],
            "inferenceConfig": {"temperature": 0.0, "maxTokens": 200},
        }
        response = self.client.converse(
            modelId=self.model_id,
            messages=body["messages"],
            inferenceConfig=body["inferenceConfig"])
        content = response["output"]["message"]["content"][0]["text"]
        return parse_rubric(content)


def parse_rubric(text: str) -> tuple[int, str]:
    """Score 1..5 + rationale from the judge's reply (tolerant of prose around the JSON)."""
    try:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            payload = json.loads(match.group(0))
            score = int(payload["score"])
            if 1 <= score <= 5:
                return score, str(payload.get("rationale", ""))[:300]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass  # fall through to the regex
    match = _SCORE_RE.search(text)
    if match:
        return int(match.group(1)), text[:300]
    raise ValueError(f"judge did not return a 1..5 score: {text[:200]!r}")