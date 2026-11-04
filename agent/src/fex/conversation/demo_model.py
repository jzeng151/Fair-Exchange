"""A deterministic demo model (#101): runs the REAL engine end to end with no AWS and no cost.

It is a Strands model, so the engine treats it exactly like Claude: it answers each structured-output request
the engine makes (IntakeTurn, PlaybackDraft, RecordSummary, ShortReply, AnswerDraft). In the retrieval call
it calls every REAL data tool once (#17); in the claim-writing call it builds claims only from the items the
engine gives it, citing their sources and a clause the standards tool returned, so the REAL citation verifier
passes them. It doesn't understand language: it follows
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
ITEMS_HEADER = "Items the data tools returned (cite only these):"


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


def _tools_called(messages: list[dict]) -> set[str]:
    return {b["toolUse"]["name"] for m in messages for b in m["content"] if "toolUse" in b}


def _items(prompt: str) -> list[dict]:
    """The items the engine put in the claim-writing prompt, one JSON object per line."""
    _, _, block = prompt.partition(ITEMS_HEADER)
    items = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                items.append(json.loads(line))
            except ValueError:
                break
        elif items:
            break
    return items


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
        yield {"messageStart": {"role": "assistant"}}
        if output is None:  # the retrieval call: every data tool once, then done
            name = next((n for n in names if n not in _tools_called(messages)), None)
            if name is None:
                yield {"contentBlockStart": {"start": {}}}
                yield {"contentBlockDelta": {"delta": {"text": "done"}}}
                yield {"contentBlockStop": {}}
                yield {"messageStop": {"stopReason": "end_turn"}}
            else:
                for event in self._tool_use(messages, name, {}):
                    yield event
        else:
            data = self._answer(prompt) if output == "AnswerDraft" else getattr(self, f"_{output}")(prompt)
            for event in self._tool_use(messages, output, data):
                yield event
        yield {"metadata": {"usage": {"inputTokens": len(prompt) // 4, "outputTokens": 50, "totalTokens": 0},
                            "metrics": {"latencyMs": 0}}}

    @staticmethod
    def _tool_use(messages: list[dict], name: str, data: dict):
        yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"demo-{len(messages)}", "name": name}}}}
        yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(data, ensure_ascii=False)}}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}

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

    def _answer(self, prompt: str) -> dict:
        """Cited claims from the items given: regional facts (else the producer's record) and peer projects,
        each citing the first clause the standards tool returned."""
        items = _items(prompt)
        clauses = [i["source"] for i in items if i["kind"] == "standard"]
        if not clauses:
            return {"insights": [], "peer_examples": []}
        facts = [i for i in items if i["kind"] == "regional"] or [i for i in items if i["kind"] == "producer_record"]
        peers = [i for i in items if i["kind"] == "peer"]

        def claim(item: dict, text: str) -> dict:
            return {"text": text, "citation": {"source": item["source"], "standard_clause": clauses[0],
                                               "period": item.get("period"), "strength": item["strength"]}}

        def peer_text(item: dict) -> str:
            data = item["data"]
            return f"{data['action']} Intended outcome: {data['intended_outcome']}" if data.get("action") else item["text"]

        return {"insights": [claim(f, f["text"]) for f in facts[:2]],
                "peer_examples": [claim(p, peer_text(p)) for p in peers[:2]]}
