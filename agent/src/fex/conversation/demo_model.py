"""A deterministic demo model (#101): runs the REAL engine end to end with no AWS and no cost.

It is a Strands model, so the engine treats it exactly like Claude: it answers each structured-output request
the engine makes (IntakeTurn, PlaybackDraft, RecordSummary, ShortReply, AnswerDraft) and, when writing an
answer, calls the REAL data tools first and builds claims only from what they returned, citing their sources
and a real APS clause, so the REAL citation verifier passes them. It doesn't understand language: it follows
the intake script, detects Spanish from simple markers, and tags from keywords. Not for producers: for local
runs, demos without AWS and integration tests. Real Claude is one setting away (FEX_DEMO_MODELS unset).
"""
import json
import re
from typing import Any

from strands.models.model import Model

OUTPUTS = ("IntakeTurn", "PlaybackDraft", "RecordSummary", "ShortReply", "AnswerDraft")

QUESTIONS = {
    "en": ["What has been most difficult for your organization lately?", "When did this start?",
           "How serious has it been?", "What have you tried so far?"],
    "es": ["¿Qué ha sido lo más difícil para su organización últimamente?", "¿Cuándo empezó?",
           "¿Qué tan grave ha sido?", "¿Qué han probado hasta ahora?"],
}
PLAYBACK = {
    "en": "Here is what I understood: {0} When: {1} How serious: {2} What you've tried: {3} Is that right?",
    "es": "Esto es lo que entendí: {0} Cuándo: {1} Gravedad: {2} Lo que han probado: {3} ¿Es correcto?",
}
SHORT_REPLY = {
    "en": "Thank you. I can help with what has been difficult for your organization.",
    "es": "Gracias. Puedo ayudarle con lo que ha sido difícil para su organización.",
}
SPANISH = re.compile(r"[ñáéíóú¿¡]|\b(el|la|los|las|que|de|y|es|una|pero|hace|muy|año)\b", re.I)

# Keyword -> challenge tag (first match wins, in this order); default climate and weather.
TAG_KEYWORDS = [
    ("market and price", ("precio", "price", "mercado", "market", "comprador", "buyer")),
    ("labor and migration", ("trabajador", "worker", "labor", "mano de obra", "migra")),
    ("water", ("agua", "water", "riego", "irrigation")),
    ("soil and land", ("suelo", "soil", "tierra", "land", "abono", "fertiliz")),
    ("financial and access to capital", ("crédito", "credit", "préstamo", "loan")),
    ("climate and weather", ("lluvia", "rain", "sequía", "drought", "clima", "weather", "calor", "heat")),
]
# Related APS clause per tag (all exist in the standards; the demo mapping the web demo also uses).
CLAUSES = {"climate and weather": "APS 4.1.1", "water": "APS 4.1.1", "soil and land": "APS 4.2.1",
           "biodiversity and conservation": "APS 4.2.1", "market and price": "APS 5.2.3",
           "labor and migration": "APS 3.3.1"}
DEFAULT_CLAUSE = "APS 1.2.2"


def _text_of(messages: list[dict]) -> str:
    return "\n".join(b.get("text", "") for m in messages if m["role"] == "user" for b in m["content"])


def _producer_lines(prompt: str) -> list[str]:
    return [line[len("producer: "):] for line in prompt.splitlines() if line.startswith("producer: ")]


def _language(prompt: str) -> str:
    said = " ".join(_producer_lines(prompt))
    if said:
        return "es" if SPANISH.search(said) else "en"
    code = re.search(r"ISO 639-1 code '([a-z]{2})'|Language so far: ([a-z]{2})|Language: ([a-z]{2})", prompt)
    found = code and next(g for g in code.groups() if g)
    return found if found in QUESTIONS else "en"


def tags_for(text: str) -> list[str]:
    lowered = text.lower()
    tags = [tag for tag, words in TAG_KEYWORDS if any(w in lowered for w in words)]
    return tags[:2] or ["climate and weather"]


def _tool_results(messages: list[dict]) -> dict[str, Any]:
    """The JSON each tool returned so far, by tool name."""
    names = {b["toolUse"]["toolUseId"]: b["toolUse"]["name"]
             for m in messages for b in m["content"] if "toolUse" in b}
    out = {}
    for m in messages:
        for b in m["content"]:
            result = b.get("toolResult")
            if result and result.get("content"):
                part = result["content"][0]
                out[names.get(result["toolUseId"], "?")] = part.get("json") or json.loads(part.get("text") or "null")
    return out


class DemoModel(Model):
    def update_config(self, **_: Any) -> None:
        pass

    def get_config(self) -> dict:
        return {"model_id": "demo"}

    async def structured_output(self, *a: Any, **k: Any):  # pragma: no cover - the engine uses tool-based output
        raise NotImplementedError
        yield

    # ------------------------------------------------------------------ streaming like a real model

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        names = [s["name"] for s in (tool_specs or [])]
        output = next((n for n in OUTPUTS if n in names), None)
        prompt = _text_of(messages)
        if output == "AnswerDraft":
            name, data = self._answer_step(prompt, messages)
        else:
            name, data = output, getattr(self, f"_{output}")(prompt)
        call_id = f"demo-{len(messages)}"
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": call_id, "name": name}}}}
        yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(data, ensure_ascii=False)}}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}
        yield {"metadata": {"usage": {"inputTokens": len(prompt) // 4, "outputTokens": 50, "totalTokens": 0},
                            "metrics": {"latencyMs": 0}}}

    # ------------------------------------------------------------------ one method per structured output

    def _IntakeTurn(self, prompt: str) -> dict:
        lang, asked = _language(prompt), len(_producer_lines(prompt))
        if asked >= len(QUESTIONS[lang]):
            return {"reply": "", "ready_for_playback": True, "language": lang}
        return {"reply": QUESTIONS[lang][asked], "ready_for_playback": False, "language": lang}

    def _PlaybackDraft(self, prompt: str) -> dict:
        lang = _language(prompt)
        said = (_producer_lines(prompt) + ["", "", "", ""])[:4]
        correction = re.search(r"The producer corrected the playback: (.+)$", prompt, re.S)
        if correction:
            said[0] = correction.group(1).strip()
        return {"text": PLAYBACK[lang].format(*said), "challenge": said[0], "timing": said[1],
                "severity": said[2], "tried": said[3], "entity_type": None, "location_disputed": False}

    def _RecordSummary(self, prompt: str) -> dict:
        lang = (re.search(r"Language: ([a-z]{2})", prompt) or [None, "en"])[1]
        pb = json.loads(re.search(r"Confirmed playback: (\{.*\})", prompt).group(1))
        original = " ".join(x for x in (pb["challenge"], pb["timing"], pb["severity"], pb["tried"]) if x)
        tags = tags_for(pb["challenge"] or original)  # what the challenge is about, not what was tried
        english = (f"The producer reports a {' and '.join(tags)} challenge. (Demo model: not a translation.)"
                   if lang != "en" else None)
        return {"summary_original": original, "summary_english": english, "tags": tags}

    def _ShortReply(self, prompt: str) -> dict:
        return {"reply": SHORT_REPLY[_language(prompt)]}

    def _answer_step(self, prompt: str, messages: list[dict]) -> tuple[str, dict]:
        """Like a model with tools: look up regional data, then peer examples, then write cited claims."""
        situation = json.loads(re.search(r"Confirmed situation: (\{.*\})", prompt).group(1))
        tag = (situation.get("tags") or ["climate and weather"])[0]
        results = _tool_results(messages)
        if "get_regional_context" not in results:
            return "get_regional_context", {}
        if "find_peer_examples" not in results:
            return "find_peer_examples", {"challenge": tag}
        clause = CLAUSES.get(tag, DEFAULT_CLAUSE)
        regional, peers = results["get_regional_context"] or {}, results["find_peer_examples"] or []
        facts = regional.get("facts", []) if isinstance(regional, dict) else []
        insights = [{"text": f["text"], "citation": {"source": f["source"], "standard_clause": clause,
                                                     "period": f.get("period"), "strength": f.get("strength", "exact")}}
                    for f in facts[:2]]
        examples = [{"text": f"{p['action']} Intended outcome: {p['intended_outcome']}",
                     "citation": {"source": p["source"], "standard_clause": clause, "strength": "nearest"}}
                    for p in (peers if isinstance(peers, list) else [])[:2]]
        return "AnswerDraft", {"insights": insights, "peer_examples": examples}
