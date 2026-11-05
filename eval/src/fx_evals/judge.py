"""The judge model for the tone and claim-support evaluators (spec 36: Amazon Nova Pro, calibrated before
its scores count). A malformed, failed or timed-out reply raises JudgeError; the evaluator then leaves the
session unscored, never scored as a pass."""
import json
import re
from typing import Any, Protocol

NOVA_PRO = "us.amazon.nova-pro-v1:0"

TONE_SYSTEM = (
    "You grade answers an advisor gave a farmer or farm business. Score the answer from 1 to 5 against this rubric: "
    "it informs rather than instructs; it hands the decision back to the producer; it uses plain language; it "
    "doesn't tell the producer what they should or must do. 5 meets every point, 1 meets none. The answer may be "
    'in English or Spanish. Reply with only JSON: {"score": <1-5>, "reason": "<one sentence>"}.'
)
SUPPORT_SYSTEM = (
    "You check whether a source supports a claim. The claim was written from the source. It is supported when "
    "every fact it states (numbers, places, names, years, what was done) appears in the source or follows "
    "directly from it. Wording may differ and the claim may be in another language. Reply with only JSON: "
    '{"supported": true|false, "reason": "<one sentence>"}.'
)


class JudgeError(Exception):
    """The judge gave no usable answer."""


class Judge(Protocol):
    model_id: str

    def tone(self, answer_text: str) -> tuple[int, str]: ...

    def supports(self, claim: str, source_text: str) -> tuple[bool, str]: ...


def _json_reply(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise JudgeError("no JSON in the judge's reply")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeError(f"malformed JSON from the judge: {exc}") from exc


class BedrockJudge:
    def __init__(self, model_id: str = NOVA_PRO, client: Any = None, region: str = "us-west-2"):
        self.model_id = model_id
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client("bedrock-runtime", region_name=region,
                                  config=Config(read_timeout=30, retries={"max_attempts": 2}))
        self.client = client

    def _ask(self, system: str, text: str) -> dict:
        try:
            response = self.client.converse(
                modelId=self.model_id, system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": text}]}],
                inferenceConfig={"maxTokens": 300, "temperature": 0})
            reply = "".join(b.get("text", "") for b in response["output"]["message"]["content"])
        except JudgeError:
            raise
        except Exception as exc:  # noqa: BLE001 - any call failure or timeout means no usable judgment
            raise JudgeError(f"judge call failed: {type(exc).__name__}") from exc
        return _json_reply(reply)

    def tone(self, answer_text: str) -> tuple[int, str]:
        reply = self._ask(TONE_SYSTEM, answer_text)
        score = reply.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            raise JudgeError(f"tone score out of range: {score!r}")
        return score, str(reply.get("reason", ""))

    def supports(self, claim: str, source_text: str) -> tuple[bool, str]:
        reply = self._ask(SUPPORT_SYSTEM, f"Source:\n{source_text}\n\nClaim:\n{claim}")
        supported = reply.get("supported")
        if not isinstance(supported, bool):
            raise JudgeError(f"supported is not true or false: {supported!r}")
        return supported, str(reply.get("reason", ""))
