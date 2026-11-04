"""Seam 1 harness for the conversation (#13): drive the entrypoint the way the chat API does.

Models are scripted Strands model subclasses (no Bedrock). Tools are the real data tools on the
real sample data. State goes through an in-memory store as JSON, so nothing survives in-process.
"""
import json
from datetime import UTC, datetime, timedelta

from fx_data.peers import ProducerProfiles
from fx_data.standards import Standards
from strands.models.model import Model
from tests.tool_harness import call_tool

from fex.conversation import ConversationEngine, InMemoryStateStore
from fex.tools.peer_examples import find_peer_examples
from fex.tools.regional_context import get_regional_context

STANDARDS = Standards.load()
CLAUSE = "APS 1.1"


class ScriptedModel(Model):
    """Plays back a script. Each step: ("tool", name, input) | ("out", ModelName, data) | ("text", str) | ("raise", exc)."""

    def __init__(self, script=()):
        self.script = list(script)
        self.calls = []  # tool names offered on each call
        self.prompts = []  # the text the model was given on each call
        self.watch = None  # optional callable run at the start of every model call (e.g. to see what was delivered)
        self.guardrail_traces = []  # Guardrail traces to attach, one per call, as Bedrock does in `metadata`

    def add(self, *steps):
        self.script.extend(steps)
        return self

    def update_config(self, **_):
        pass

    def get_config(self):
        return {}

    async def structured_output(self, *a, **k):  # pragma: no cover
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.calls.append([s["name"] for s in (tool_specs or [])])
        if self.watch:
            self.watch()
        self.prompts.append(" ".join(b.get("text", "") for m in messages if m["role"] == "user" for b in m["content"]))
        if not self.script:
            raise AssertionError("ScriptedModel ran out of script")
        kind, *rest = self.script.pop(0)
        if kind == "raise":
            raise rest[0]
        trace = self.guardrail_traces.pop(0) if self.guardrail_traces else None
        yield {"messageStart": {"role": "assistant"}}
        if kind in ("tool", "out"):
            name, data = rest
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"t{len(self.calls)}", "name": name}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(data)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
            if trace:
                yield {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
                                    "metrics": {"latencyMs": 1}, "trace": {"guardrail": trace}}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": rest[0]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}


def cauca_producer() -> str:
    profiles = ProducerProfiles.load()._profiles
    return next(pid for pid, p in profiles.items() if p["region"] == "Cauca")


def real_sources(producer_id: str) -> tuple[list[dict], list[dict]]:
    """What the real tools return for this producer, so scripted claims can cite real sources."""
    state = {"producer_id": producer_id, "step": "respond"}
    _, regional = call_tool(get_regional_context, {}, state)
    _, peers = call_tool(find_peer_examples, {"challenge": "water"}, state)
    return regional["facts"], peers


def claim(text: str, source: str, clause: str = CLAUSE) -> dict:
    return {"text": text, "citation": {"source": source, "standard_clause": clause}}


# Structured outputs the small model produces
def intake(reply: str, ready: bool = False, language: str = "es") -> tuple:
    return ("out", "IntakeTurn", {"reply": reply, "ready_for_playback": ready, "language": language})


def playback(text: str = "Entiendo: la lluvia bajó y la cosecha cayó.", entity_type: str | None = None,
             location_disputed: bool = False) -> tuple:
    return ("out", "PlaybackDraft", {"text": text, "challenge": "Poca lluvia", "timing": "Dos temporadas",
                                     "severity": "Alta", "tried": "Nada aún", "entity_type": entity_type,
                                     "location_disputed": location_disputed})


def summary() -> tuple:
    return ("out", "RecordSummary", {"summary_original": "La lluvia bajó.", "summary_english": "Rain fell.",
                                     "tags": ["water", "climate and weather"]})


def short_reply(text: str = "Claro.") -> tuple:
    return ("out", "ShortReply", {"reply": text})


def answer(insights: list[dict], peers: list[dict]) -> tuple:
    return ("out", "AnswerDraft", {"insights": insights, "peer_examples": peers})


RETRIEVE = (("tool", "get_regional_context", {}), ("tool", "find_peer_examples", {"challenge": "water"}))


class Run:
    """One conversation against a fresh engine."""

    def __init__(self, producer_id: str | None = None, profiles=None, records=None, scope_check=None):
        self.producer_id = producer_id or cauca_producer()
        self.conversation_id = "conv-1"
        self.small, self.large = ScriptedModel(), ScriptedModel()
        self.store = InMemoryStateStore()
        self.now = datetime(2026, 11, 4, 12, tzinfo=UTC)
        kwargs = {"profiles": profiles} if profiles else {}
        if records is not None:
            kwargs["records"] = records
        if scope_check is not None:
            kwargs["scope_check"] = scope_check
        self.engine = ConversationEngine(store=self.store, small_model=self.small, large_model=self.large,
                                         standards=STANDARDS, clock=self._clock, **kwargs)
        self.regional, self.peers = real_sources(self.producer_id)

    def _clock(self):
        self.now += timedelta(seconds=1)
        return self.now

    def send(self, kind: str, **fields):
        return self.engine.handle({"kind": kind, "producerId": self.producer_id,
                                   "conversationId": self.conversation_id, **fields})

    def action(self, name: str, **args):
        return self.send("action", action={"name": name, "args": args})

    def state(self):
        return self.store.load(self.producer_id, self.conversation_id)

    # Conveniences that walk the happy path
    def good_answer(self):
        return answer([claim("Rainfall fell.", self.regional[0]["source"])],
                      [claim("A peer built tanks.", self.peers[0]["source"])])

    def to_playback(self):
        self.small.add(intake("¿Qué ha sido difícil?"), intake("", ready=True), playback())
        self.send("start")
        return self.send("message", text="La lluvia bajó mucho y la cosecha cayó.")

    def to_consent(self):
        self.to_playback()
        self.small.add(summary())
        self.large.add(*RETRIEVE, self.good_answer())
        return self.action("confirm_playback")

    def to_feedback(self):
        self.to_consent()
        return self.action("set_consent", scope="internal")


def types(events) -> list[str]:
    return [e.type for e in events]


def of(events, kind: str) -> list:
    return [e for e in events if e.type == kind]


def last_step(events) -> str:
    return of(events, "step")[-1].step


def allowed(events) -> list[str]:
    return of(events, "actions")[-1].allowed
