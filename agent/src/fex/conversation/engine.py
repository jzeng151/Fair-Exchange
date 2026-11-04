"""The conversation entrypoint (issue #13). Spec: docs/specs/13-conversation-steps.md.

Code holds the step and decides when it changes; the model only writes words.
  - Each request is validated, the state is rebuilt from the store, one step function runs, the state is saved.
  - The small model handles intake, playback, tagging and short replies. It is never offered data tools.
  - In `respond` the large model first calls the data tools. Code then calls any data tool the model
    skipped (`tool_backstopped`, #17), and only then does the large model write claims, from every item
    returned. Each claim is checked by the citation verifier before it is sent; failures are rewritten,
    then dropped with their reason codes in the decision log.
"""
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fx_data.peers import ProducerProfiles
from fx_data.standards import Standards
from pydantic import BaseModel, Field, TypeAdapter
from strands import Agent

from fex.conversation import copy
from fex.conversation.scope import ScopeCheck, always_in_scope
from fex.conversation.contract import (
    ActionEntry, ActionName, Answer, Event, Request, ResumeResponse, SpokenEntry,
)
from fex.guardrail import CONVERSATION_KEY, OutputAssessor, narrative_texts
from fex.conversation.state import (
    ConversationState, DecisionLogEntry, Playback, Profile, ShownClaims, StateConflict, StateStore,
)
from fex.models import ChallengeTag, Claim, ConsentChoice, EarlierAnswer
from fex.tools import ALL_TOOLS, DATA_TOOLS
from fex.tools._contract import EVIDENCE_KEY, ITEMS_KEY, TOOLS_RUN_KEY, run_data_tool
from fex.tools.standards import RETRIEVER_KEY, ClauseRetriever, default_retriever
from fex.verifier import Problem, SessionEvidence, check_claim

log = logging.getLogger(__name__)
_REQUEST = TypeAdapter(Request)
_EVENT = TypeAdapter(Event)

# ------------------------------------------------------------------ structured outputs the models write


class IntakeTurn(BaseModel):
    """One intake reply. Set ready_for_playback once challenge, timing, severity and what was tried are known."""

    reply: str = Field(description="The next question or acknowledgement, in the producer's language")
    ready_for_playback: bool
    language: str = Field(description="ISO 639-1 code of the producer's language, e.g. 'es'")


class PlaybackDraft(BaseModel):
    """FEX's restatement of the producer's situation, to be confirmed or corrected."""

    text: str = Field(description="Plain restatement in the producer's language")
    challenge: str
    timing: str
    severity: str
    tried: str
    entity_type: str | None = Field(default=None, description="Only if the producer corrected their entity type")
    location_disputed: bool = Field(default=False, description="True if the producer says the location on file is wrong")


class RecordSummary(BaseModel):
    """Summaries and tags generated once, from the confirmed playback."""

    summary_original: str
    summary_english: str | None = Field(description="English summary; required when the conversation is not in English")
    tags: list[ChallengeTag] = Field(min_length=1)


class ShortReply(BaseModel):
    """A short reply to typed text outside intake and playback. Never changes anything."""

    reply: str


class AnswerDraft(BaseModel):
    """Claims for the producer. Every claim cites a source a tool returned and a real APS/FPS clause."""

    insights: list[Claim] = Field(default_factory=list)
    peer_examples: list[Claim] = Field(default_factory=list)


# ------------------------------------------------------------------------------------------ prompts

_RULES = (
    "You are FEX, a computer assistant for Fair Trade producers. Rules: plain, short sentences in the producer's "
    "language; never tell the producer what they should do (no 'you should', 'we recommend', 'the best option'); "
    "share information neutrally; the decision is theirs."
)
INTAKE_SYSTEM = _RULES + (
    " You are in intake. Open with an open question about what has been difficult. Then ask, one at a time, when it "
    "started, how severe it is and what they have tried. Confirm their location and entity type from the profile "
    "instead of asking them to type it. Set ready_for_playback when you know all four."
)
PLAYBACK_SYSTEM = _RULES + (
    " Restate what you understood: the challenge, timing, severity and what was tried. If the producer corrected "
    "their entity type, set entity_type. If they say the location on file is wrong, set location_disputed; never "
    "use a different location."
)
SUMMARY_SYSTEM = (
    "Summarize the confirmed playback in the producer's own words (summary_original) and in English "
    "(summary_english; required unless the language is English). Tag it with one or more of the 11 challenge tags. "
    "If a location note is given, say in both summaries that the producer disputes the location on file."
)
SHORT_REPLY_SYSTEM = _RULES + (
    " Answer the producer's typed question in one or two sentences. You cannot change their consent, feedback or "
    "the conversation's step, and you cannot look anything up now."
)
RETRIEVE_SYSTEM = (
    "You are FEX's retrieval step. Call every data tool once: this producer's record, regional data, peer "
    "examples and the related Fair Trade standard clauses. The tools take no arguments; they already know the "
    "producer and the confirmed challenge. When all have returned, reply with the single word: done."
)
ANSWER_SYSTEM = _RULES + (
    " Write insights (what the data shows, citing the producer's record or regional data) and peer_examples "
    "(what comparable producers tried, with trade-offs, citing a peer project) using only the items given. Every "
    "claim must copy an item's `source` exactly into citation.source, and set citation.standard_clause to the "
    "most related clause ID from the `standard` items. Only state facts the items contain."
)

# ------------------------------------------------------------------------------------------- engine

ALLOWED: dict[str, list[ActionName]] = {
    "intake": ["end"],
    "playback": ["confirm_playback", "correct_playback", "end"],
    "respond": ["reopen_playback", "end"],  # + retry_answer after an error
    "consent": ["reopen_playback", "set_consent", "end"],
    "feedback": ["reopen_playback", "set_consent", "set_feedback", "end"],
    "closed": [],
}


def allowed_actions(state: ConversationState) -> list[ActionName]:
    actions = list(ALLOWED[state.step])
    if state.step == "respond" and state.answer_failed:
        actions.insert(1, "retry_answer")
    return actions


def _default_profiles() -> Callable[[str], Profile | None]:
    table = ProducerProfiles.load()

    def lookup(producer_id: str) -> Profile | None:
        p = table.get(producer_id)
        return Profile(producer_id=producer_id, country=p.country, region=p.region, crop=p.crop,
                       entity_type=p.entity_type) if p else None
    return lookup


def _tool_errors(messages: list[dict]) -> list[str]:
    """Tool calls that failed. Strands returns a failure as a toolResult with status "error", not an exception."""
    return [" ".join(part.get("text", "") for part in block["toolResult"].get("content", []))[:200]
            for message in messages for block in message["content"]
            if block.get("toolResult", {}).get("status") == "error"]


_BRACKET_ID = re.compile(r"\[([^\[\]]+)\]\s*$")


def _claim_refs(claim: Claim) -> list[str]:
    """Opaque IDs for the decision log: the source's bracketed item ID and the clause ID. No free text."""
    refs = []
    if match := _BRACKET_ID.search(claim.citation.source):
        refs.append(match.group(1))
    clause = claim.citation.standard_clause.split()
    if len(clause) == 2 and clause[0].upper() in ("APS", "FPS"):
        refs.append(f"{clause[0].upper()} {clause[1]}")
    return refs


class _Turn:
    """Events for one request, numbered in order. Each event goes to `on_event` the moment it is created,
    so text and checked claims reach the producer while later model calls are still running."""

    def __init__(self, on_event: Callable[[Any], None] | None = None) -> None:
        self.events: list = []
        self.on_event = on_event
        self.spoken: list[str] = []
        self.excluded = False  # an out-of-scope exchange (#21): kept in history, hidden from models
        self.loaded_revision: int | None = None  # the state revision this request started from

    def emit(self, type_: str, **fields) -> None:
        event = _EVENT.validate_python({"type": type_, "seq": len(self.events) + 1, **fields})
        self.events.append(event)
        if self.on_event:
            self.on_event(event)

    def say(self, text: str) -> None:
        """Text streams word by word as `text` events."""
        if not text:
            return
        for chunk in re.findall(r"\S+\s*", text):
            self.emit("text", text=chunk)
        self.spoken.append(text)


class _AgentFailed(Exception):
    pass


class ConversationEngine:
    def __init__(self, *, store: StateStore, small_model: Any, large_model: Any, standards: Standards | None = None,
                 profiles: Callable[[str], Profile | None] | None = None, tools: list | None = None,
                 retriever: ClauseRetriever | None = None,
                 clock: Callable[[], datetime] | None = None, max_retries: int = 2,
                 records: Any = None, scope_check: ScopeCheck | None = None,
                 pii_scanner: Callable[[str, str], list[dict]] | None = None,
                 output_assessor: OutputAssessor | None = None) -> None:
        self.store = store
        self.small_model, self.large_model = small_model, large_model
        self.standards = standards or Standards.load()
        self.profiles = profiles or _default_profiles()
        self.tools = tools if tools is not None else ALL_TOOLS
        self.pii_scanner = pii_scanner  # the Comprehend seam (#20): None in tests, wired in runtime
        self.retriever = retriever if retriever is not None else default_retriever()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.max_retries = max_retries
        self.records = records  # a fex.records.RecordStore; None = records are not saved (#26)
        self.scope_check = scope_check or always_in_scope  # how it decides is "Not decided" (#21)
        # Assesses structured-output text, which the Converse guardrail skips (#12). No-op when unconfigured.
        self.output_assessor = output_assessor or OutputAssessor()

    # ------------------------------------------------------------------ entrypoint

    def handle(self, payload: dict, on_event: Callable[[Any], None] | None = None) -> list | ResumeResponse:
        """Validate a request and run it. Raises ValueError for a malformed request.

        Returns every event of the turn. With `on_event`, each event is also delivered as soon as it exists
        (streaming); the returned list is the same events.
        """
        request = _REQUEST.validate_python(payload)
        state = self.store.load(request.producer_id, request.conversation_id)
        turn = _Turn(on_event)
        turn.loaded_revision = state.revision if state else None

        if request.kind == "start":
            state = state or self._new_state(request.producer_id, request.conversation_id)
            if not state.history:  # a repeated start just reports where the conversation is
                # Opening language (#22): the profile's language if it has one, otherwise English. Nobody has
                # written yet, so the model's guess doesn't set it; intake switches once the producer writes.
                state.language = state.profile.language or "en"
                opening = self._structured(
                    state, self.small_model, INTAKE_SYSTEM,
                    self._transcript(state) + f"\n\nStart the conversation with an open question, written in the "
                    f"language with ISO 639-1 code '{state.language}'.", IntakeTurn)
                turn.say(opening.reply)
            return self._finish(state, turn, step_changed=True)

        if state is None:
            turn.emit("error", code="invalid_action", message="Unknown conversation.")
            return self._events(turn, None)

        if request.kind == "resume":
            return ResumeResponse(step=state.step, language=state.language, allowed=allowed_actions(state),
                                  answer=state.answer, history=state.history)

        if state.step == "closed":
            turn.emit("error", code="closed", message=copy.text(state.language, "closed"))
            return self._events(turn, None)

        if request.kind == "auto_close":
            return self._close(state, turn, request.reason)
        if request.kind == "message":
            return self._message(state, turn, request.text)
        return self._action(state, turn, request.action.name, request.action.args.model_dump())

    # ------------------------------------------------------------------ requests

    def _message(self, state: ConversationState, turn: _Turn, text: str):
        before = state.step
        state.history.append(SpokenEntry(role="producer", text=text, at=self.clock()))
        if self._declined(state, turn, text):
            return self._finish(state, turn, step_changed=False)
        if state.step == "intake":
            self._intake(state, turn)
        elif state.step == "playback":
            self._playback(state, turn, correction=text)
        else:  # respond, consent, feedback: a short reply that changes nothing
            reply = self._structured(state, self.small_model, SHORT_REPLY_SYSTEM, self._transcript(state), ShortReply)
            turn.say(reply.reply)
        return self._finish(state, turn, step_changed=state.step != before)

    def _action(self, state: ConversationState, turn: _Turn, name: str, args: dict):
        if name not in allowed_actions(state):
            turn.emit("error", code="invalid_action", message=copy.text(state.language, "invalid"))
            return self._events(turn, state)
        if self._is_repeat(state, name, args):
            return self._finish(state, turn, step_changed=False, save=False)

        before = state.step
        state.history.append(ActionEntry(role="action", name=name, args=args, at=self.clock()))
        if name == "confirm_playback":
            self._confirm(state, turn)
        elif name == "correct_playback":
            if not self._declined(state, turn, args["text"]):  # a correction gets the same scope check (#21)
                self._playback(state, turn, correction=args["text"])
        elif name == "reopen_playback":
            self._reopen(state, turn)
        elif name == "retry_answer":
            self._retire_partial(state)
            self._respond(state, turn)
        elif name == "set_consent":
            self._set_consent(state, args["scope"])
            self._save_record(state, turn)
        elif name == "set_feedback":
            state.feedback = args["value"]
            self._save_record(state, turn)
        elif name == "end":
            return self._close(state, turn, "end")
        return self._finish(state, turn, step_changed=state.step != before)

    def _declined(self, state: ConversationState, turn: _Turn, text: str) -> bool:
        """The one scope check for producer text (#21). Out of scope: fixed decline in the producer's language,
        no model, no data tool, step unchanged; the exchange stays in history but is hidden from models."""
        verdict = self.scope_check(text, state.step)
        if verdict.in_scope:
            return False
        if verdict.language:
            state.language = verdict.language
        state.excluded_history.append(len(state.history) - 1)
        turn.excluded = True
        turn.say(copy.text(state.language, f"out_of_scope_{verdict.reason or 'other_producer_data'}"))
        turn.say(copy.text(state.language, "back_to_open"))
        return True

    @staticmethod
    def _is_repeat(state: ConversationState, name: str, args: dict) -> bool:
        """Repeating a choice the state already holds changes nothing (safe retries)."""
        return (name == "set_consent" and args["scope"] == state.consent) or \
               (name == "set_feedback" and args["value"] == state.feedback)

    def _close(self, state: ConversationState, turn: _Turn, reason: str):
        state.step, state.closed_reason, state.closed_at = "closed", reason, self.clock()
        self._save_record(state, turn)
        return self._finish(state, turn, step_changed=True)

    def _save_record(self, state: ConversationState, turn: _Turn) -> None:
        """Save point (#26): code saves the record; each save emits `record_saved`.
        A conflict or invalid record is logged and surfaced as an error, never retried."""
        if self.records is None:
            return
        from fex.records import RecordConflict, save_record  # local: records imports conversation state

        try:
            result = save_record(state, self.records, self.clock(), pii_scanner=self.pii_scanner)
        except (RecordConflict, ValueError) as exc:
            log.error("record not saved for conversation %s: %s", state.conversation_id, exc)
            turn.emit("error", code="agent_failed", message="Your answer could not be saved. Please try again.")
            return
        if result:
            turn.emit("record_saved", status=result.status, consent_scope=result.consent_scope,
                      version=result.version)

    # ------------------------------------------------------------------ steps

    def _ask(self, state: ConversationState, turn: _Turn, system: str, prompt: str) -> IntakeTurn:
        result = self._structured(state, self.small_model, system, prompt, IntakeTurn)
        state.language = result.language or state.language
        return result

    def _intake(self, state: ConversationState, turn: _Turn) -> None:
        result = self._ask(state, turn, INTAKE_SYSTEM, self._transcript(state))
        if result.ready_for_playback:
            self._playback(state, turn)
        else:
            turn.say(result.reply)

    def _playback(self, state: ConversationState, turn: _Turn, correction: str | None = None) -> None:
        prompt = self._transcript(state) + (f"\n\nThe producer corrected the playback: {correction}" if correction else "")
        draft = self._structured(state, self.small_model, PLAYBACK_SYSTEM, prompt, PlaybackDraft)
        state.playback = Playback(text=draft.text, challenge=draft.challenge, timing=draft.timing,
                                  severity=draft.severity, tried=draft.tried)
        if draft.entity_type:  # every correction applies; back to the value on file clears the override
            state.entity_type = None if draft.entity_type == state.profile.entity_type else draft.entity_type
        state.step = "playback"
        turn.say(draft.text)
        if draft.location_disputed:
            state.location_note = "The producer says the location on file is wrong; the location on file was kept."
            place = ", ".join(p for p in (state.profile.region, state.profile.country) if p) or "?"
            turn.say(copy.text(state.language, "location_kept", place=place))

    def _confirm(self, state: ConversationState, turn: _Turn) -> None:
        assert state.playback is not None
        note = f"\nLocation note (keep it in both summaries): {state.location_note}" if state.location_note else ""
        summary = self._structured(state, self.small_model, SUMMARY_SYSTEM,
                                   f"Language: {state.language}\nConfirmed playback: {state.playback.model_dump_json()}"
                                   + note, RecordSummary)
        state.playback.summary_original = summary.summary_original
        state.playback.summary_english = None if state.language == "en" else summary.summary_english
        state.playback.tags = summary.tags
        state.playback.confirmed = True
        state.step = "respond"
        self._emit_step(state, turn)
        self._respond(state, turn)

    def _reopen(self, state: ConversationState, turn: _Turn) -> None:
        if state.answer:
            state.earlier_answers.append(EarlierAnswer(**state.answer.model_dump(), reason="reopened",
                                                       given_at=state.answer_given_at or self.clock()))
        self._retire_partial(state)
        state.answer, state.answer_failed = None, False
        state.consent, state.feedback = None, None
        if state.playback:
            state.playback.confirmed = False
            turn.say(state.playback.text)
        state.step = "playback"

    def _retire_partial(self, state: ConversationState) -> None:
        """Claims already shown in an unfinished answer are kept as an earlier answer (reason `interrupted`)."""
        if state.partial and (state.partial.insights or state.partial.peer_examples):
            state.earlier_answers.append(EarlierAnswer(insights=state.partial.insights,
                                                       peer_examples=state.partial.peer_examples,
                                                       reason="interrupted",
                                                       given_at=state.partial_started_at or self.clock()))
        state.partial, state.partial_started_at = None, None

    def _set_consent(self, state: ConversationState, scope: str) -> None:
        state.consent = scope
        state.consent_history.append(ConsentChoice(scope=scope, recorded_at=self.clock()))
        if scope == "declined":
            state.feedback = None
            state.step = "consent"
        else:
            state.step = "feedback"

    # ------------------------------------------------------------------ the answer

    def _respond(self, state: ConversationState, turn: _Turn) -> None:
        state.step, state.answer, state.answer_failed = "respond", None, False
        state.partial, state.partial_started_at = ShownClaims(), self.clock()
        lang = state.language
        try:
            turn.say(copy.text(lang, "respond_opening"))
            evidence = state.session_evidence()
            items = self._retrieve(state, evidence)  # every data tool has run before any claim is written
            draft = self._write(state, self._answer_prompt(state, items))
            pending = [("insights", c) for c in draft.insights] + [("peer_examples", c) for c in draft.peer_examples]
            for attempt in range(self.max_retries + 1):
                failed = []
                for section, claim in pending:
                    problems = self._check(section, claim, evidence)
                    if problems:
                        failed.append((section, claim, problems))
                        continue
                    getattr(state.partial, section).append(claim)
                    turn.emit("claim", section=section, claim=claim.model_dump())
                if not failed:
                    break
                if attempt == self.max_retries:
                    for section, claim, problems in failed:
                        codes = sorted({p.code for p in problems})
                        log.warning("dropped unverified claim (%s): %s", section, ", ".join(codes))
                        for code in codes:
                            self._log(state, "verifier", code, _claim_refs(claim))
                    break
                draft = self._write(state, self._rewrite_prompt(state, items, failed))
                pending = [("insights", c) for c in draft.insights] + [("peer_examples", c) for c in draft.peer_examples]
        except _AgentFailed as exc:
            log.warning("answer failed: %s", exc)
            state.answer_failed = True
            turn.say(copy.text(lang, "failed"))
            turn.emit("error", code="agent_failed", message=copy.text(lang, "failed"))
            return

        shown = state.partial
        evidence_level = "full" if shown.insights and shown.peer_examples else "limited"
        if not shown.insights:
            turn.say(copy.text(lang, "no_insights"))
        if not shown.peer_examples:
            turn.say(copy.text(lang, "no_peers"))
        turn.say(copy.text(lang, "hand_back"))
        state.answer = Answer(insights=shown.insights, peer_examples=shown.peer_examples, evidence=evidence_level)
        state.answer_given_at = state.partial_started_at
        state.partial, state.partial_started_at = None, None
        turn.emit("answer", insights=[c.model_dump() for c in shown.insights],
                  peer_examples=[c.model_dump() for c in shown.peer_examples], evidence=evidence_level)
        state.step = "consent"

    def _check(self, section: str, claim: Claim, evidence: SessionEvidence) -> list[Problem]:
        return check_claim(section, claim, evidence, self.standards)

    def _log(self, state: ConversationState, kind: str, code: str, refs: list[str]) -> None:
        state.decision_log.append(DecisionLogEntry(at=self.clock(), kind=kind, code=code, refs=refs))

    def _retrieve(self, state: ConversationState, evidence: SessionEvidence) -> list[dict]:
        """The model calls the data tools; code then calls any it skipped (#17). Returns every item returned
        in this respond step. Tools add their items to `evidence`, which is kept in the conversation state."""
        pb = state.playback
        tools_run: set[str] = set()
        items: list[dict] = []
        invocation_state = {
            "producer_id": state.producer_id, "step": "respond", "entity_type": state.effective_entity_type,
            "tags": list(pb.tags) if pb else [], "summary_english": pb.summary_english if pb else None,
            "summary_original": pb.summary_original if pb else None,
            CONVERSATION_KEY: state.conversation_id,  # for Guardrail findings (#12)
            RETRIEVER_KEY: self.retriever, EVIDENCE_KEY: evidence, TOOLS_RUN_KEY: tools_run, ITEMS_KEY: items,
        }
        try:
            try:
                agent = Agent(model=self.large_model, system_prompt=RETRIEVE_SYSTEM, tools=list(self.tools),
                              callback_handler=None)
                agent(self._situation(state), invocation_state=invocation_state)
            except Exception as exc:  # model failure, or a tool failure Strands raised
                raise _AgentFailed(str(exc)) from exc
            if errors := _tool_errors(agent.messages):  # a tool failure Strands returned as a result
                raise _AgentFailed("data tool failed: " + "; ".join(errors))
            for tool in self.tools:
                data_tool = DATA_TOOLS.get(tool.tool_name)
                if data_tool is None or data_tool.name in tools_run:
                    continue
                self._log(state, "tool", "tool_backstopped", [data_tool.name])
                try:
                    run_data_tool(data_tool, invocation_state)
                except Exception as exc:
                    raise _AgentFailed(f"data tool failed: {data_tool.name}: {exc}") from exc
        finally:
            state.keep_evidence(evidence)
        return items

    def _write(self, state: ConversationState, prompt: str) -> AnswerDraft:
        """The large model writes claims from the items. No tools are offered here."""
        try:
            agent = Agent(model=self.large_model, system_prompt=ANSWER_SYSTEM, tools=[], callback_handler=None)
            draft = agent(prompt, structured_output_model=AnswerDraft,
                          invocation_state={CONVERSATION_KEY: state.conversation_id}).structured_output
        except Exception as exc:
            raise _AgentFailed(str(exc)) from exc
        self.output_assessor.assess(narrative_texts(draft), state.conversation_id)
        return draft

    def _situation(self, state: ConversationState) -> str:
        pb = state.playback
        return (f"Language: {state.language}\nEntity type: {state.effective_entity_type}\n"
                f"Confirmed situation: {pb.model_dump_json(include={'challenge', 'timing', 'severity', 'tried', 'tags'})}")

    def _answer_prompt(self, state: ConversationState, items: list[dict]) -> str:
        # Drop only exact repeats (the model calling a tool twice). Distinct facts can share a source label
        # (e.g. every survey fact), so the label alone is not an identity.
        seen, unique = set(), []
        for item in items:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return (self._situation(state) + "\n\nItems the data tools returned (cite only these):\n"
                + "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in unique))

    def _rewrite_prompt(self, state: ConversationState, items: list[dict], failed: list) -> str:
        lines = [f"- [{section}] {claim.text} (source: {claim.citation.source}; clause: "
                 f"{claim.citation.standard_clause}) -> {', '.join(p.code for p in problems)}: "
                 f"{'; '.join(p.reason for p in problems)}"
                 for section, claim, problems in failed]
        return (self._answer_prompt(state, items) + "\n\nThese claims failed the citation check. Rewrite only "
                "these, citing sources and clause IDs exactly as the items give them and without directive "
                "language, or leave them out:\n" + "\n".join(lines))

    # ------------------------------------------------------------------ helpers

    def _structured(self, state: ConversationState, model: Any, system: str, prompt: str,
                    output: type[BaseModel]) -> Any:
        """Small-model calls: no data tools are ever offered here."""
        agent = Agent(model=model, system_prompt=system, tools=[], callback_handler=None)
        # Only the conversation ID: no producer ID, step or entity type, so no data tool could ever run.
        result = agent(prompt, structured_output_model=output,
                       invocation_state={CONVERSATION_KEY: state.conversation_id}).structured_output
        self.output_assessor.assess(narrative_texts(result), state.conversation_id)
        return result

    def _transcript(self, state: ConversationState) -> str:
        p = state.profile
        lines = [f"Profile on file: location {p.region}, {p.country}; crop {p.crop}; "
                 f"entity type {state.effective_entity_type}. Language so far: {state.language}."]
        hidden = set(state.excluded_history)
        for i, h in enumerate(state.history):
            if h.role in ("producer", "fex") and i not in hidden:
                lines.append(f"{h.role}: {h.text}")
        choices = [f"{name}: {value}" for name, value in (("consent", state.consent), ("feedback", state.feedback))
                   if value]
        if choices:  # button choices are actions, not spoken history
            lines.append("The producer's current choices: " + "; ".join(choices) + ".")
        shown = state.answer or state.partial
        if shown and (shown.insights or shown.peer_examples):  # claims are events, not spoken history
            lines.append("FEX showed these checked points (insights, then peer examples):")
            lines += [f"- {c.text} (source: {c.citation.source})" for c in shown.insights + shown.peer_examples]
        return "\n".join(lines)

    def _new_state(self, producer_id: str, conversation_id: str) -> ConversationState:
        profile = self.profiles(producer_id) or Profile(producer_id=producer_id)
        now = self.clock()
        return ConversationState(producer_id=producer_id, conversation_id=conversation_id, profile=profile,
                                 started_at=now, updated_at=now)

    def _emit_step(self, state: ConversationState, turn: _Turn) -> None:
        turn.emit("step", step=state.step, language=state.language)

    def _finish(self, state: ConversationState, turn: _Turn, *, step_changed: bool, save: bool = True):
        if turn.spoken:
            state.history.append(SpokenEntry(role="fex", text=" ".join(turn.spoken), at=self.clock()))
            if turn.excluded:
                state.excluded_history.append(len(state.history) - 1)
        steps = [e.step for e in turn.events if e.type == "step"]
        if not steps or steps[-1] != state.step:
            self._emit_step(state, turn)
        turn.emit("actions", allowed=allowed_actions(state), language=state.language)
        if save:
            state.updated_at = self.clock()
            try:
                self.store.save(state, expected_revision=turn.loaded_revision)
            except StateConflict as exc:  # a newer turn already saved: never overwrite it
                log.error("stale turn not saved: %s", exc)
                turn.emit("error", code="agent_failed",
                          message="This conversation changed while I was answering. Please reload it.")
        return self._events(turn, state)

    @staticmethod
    def _events(turn: _Turn, state: ConversationState | None) -> list:
        turn.emit("done")
        return list(turn.events)
