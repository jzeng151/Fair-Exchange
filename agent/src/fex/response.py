"""Grounded response pipeline (issue #18).

The large model writes the answer one claim per line, shaped
``{"section": "insights" | "peer_examples", "claim": <Claim>}``. This module
parses each completed line, checks it against the citation verifier (#17), and
emits passing claims at once as ``claim`` events ([#13 spec](13-conversation-steps.md)).

Owned here: the line parser, the emit-after-check pipeline (3 + 3 caps, duplicate
drops, immutable emitted claims, follow-ups for open slots only), the prompt rules,
and the fixed text. Retrieval is out of scope (#14-#17); the state machine, the real
model client and the event schemas belong to #13 — this module only requires that
the writer hand it complete lines and emits through a plain callable.
"""
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from fx_data.standards import Standards
from pydantic import BaseModel, ConfigDict, ValidationError

from fex.models import Claim
from fex.verifier import SessionEvidence, verify

SECTIONS = ("insights", "peer_examples")
SECTION_LIMIT = 3
MAX_FOLLOWUPS = 2  # first pass + up to 2 follow-up calls (verifier retry limit)


class ClaimLine(BaseModel):
    """One model line: which section the claim belongs to, and the claim itself."""

    model_config = ConfigDict(extra="forbid")

    section: str
    claim: Claim


def normalize(text: str) -> str:
    """'  La  lluvia  fue BAJA. ' -> 'la lluvia fue baja.' — accent-insensitive identity."""
    decomposed = unicodedata.normalize("NFKD", text.lower().strip())
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", folded)


# --- Line parsing -------------------------------------------------------------

def parse_claim_line(line: str) -> ClaimLine | None:
    """Parse one model line. Blank lines return None (nothing is fed to the model twice).

    Anything that is not a valid ``ClaimLine`` raises ValueError: the caller records
    it as a failed claim with reason `malformed` ([#18 spec](../specs/18-grounded-response.md)).
    """
    text = line.strip()
    if not text:
        return None
    try:
        return ClaimLine.model_validate(json.loads(text))
    except (ValueError, ValidationError) as exc:
        raise ValueError("malformed") from exc


# --- The check ----------------------------------------------------------------

def default_check(claim: Claim, section: str, evidence: SessionEvidence,
                  standards: Standards) -> list[str]:
    """Check one claim with the merged verifier (#17). Returns reason codes for failures.

    The approved #17 spec adds per-claim reasons (clause set, source kind, directive
    language) to the verifier. When those land, this adapter is replaced by that
    per-claim function; every caller here only needs 'callable -> list of reasons'.
    """
    insights = [claim] if section == "insights" else []
    peers = [claim] if section == "peer_examples" else []
    return [p.reason for p in verify(insights, peers, evidence, standards).problems]


# --- Streaming writer -----------------------------------------------------------

EmitFn = Callable[[int, str, Claim], None]  # (claim_id, section, claim) -> a `claim` event


@dataclass
class LineOutcome:
    """What a fed line did: emitted / duplicate / ignored (section full) / failed."""

    status: str  # "emitted", "duplicate", "ignored", "failed"
    claim_id: int | None = None
    reasons: list[str] = field(default_factory=list)


class GroundedResponseWriter:
    """Feeds lines one at a time; emits passing claims as they are checked.

    Emitted claims are immutable: nothing rewrites or withdraws what was already
    shown. Duplicates (same section, source and normalized text) are dropped, and
    once a section holds 3 emitted claims further lines for it are ignored.
    """

    def __init__(self, evidence: SessionEvidence, standards: Standards, emit: EmitFn,
                 check: Callable[[Claim, str], list[str]] | None = None):
        self.evidence, self.standards, self.emit = evidence, standards, emit
        self.check = check or (lambda c, s: default_check(c, s, evidence, standards))
        self.emitted: dict[str, list[tuple[int, Claim]]] = {s: [] for s in SECTIONS}
        self.failed: list[dict] = []  # pending failures, awaiting replacement
        self.dropped_history: list[dict] = []  # failed lines already handed to a follow-up
        self.duplicates = 0
        self.overflow = 0
        self._ids = {}  # (section, source, normalized text) -> claim_id
        self._next_id = 1

    def feed(self, line: str) -> LineOutcome:
        try:
            parsed = parse_claim_line(line)
        except ValueError as exc:
            reasons = [str(exc)]
            self.failed.append({"line": line, "reasons": reasons})
            return LineOutcome("failed", reasons=reasons)
        if parsed is None:
            return LineOutcome("ignored")  # blank lines are noise, not failed claims

        section, claim = parsed.section, parsed.claim
        if section not in SECTIONS:
            reasons = ["malformed"]
            self.failed.append({"line": line, "reasons": reasons})
            return LineOutcome("failed", reasons=reasons)
        identity = (section, claim.citation.source, normalize(claim.text))
        if identity in self._ids:
            self.duplicates += 1
            return LineOutcome("duplicate", claim_id=self._ids[identity])
        if len(self.emitted[section]) >= SECTION_LIMIT:
            self.overflow += 1
            return LineOutcome("ignored")
        reasons = self.check(claim, section)
        if reasons:
            self.failed.append({"line": line, "reasons": reasons})
            return LineOutcome("failed", reasons=reasons)
        claim_id = self._next_id
        self._next_id += 1
        self._ids[identity] = claim_id
        self.emitted[section].append((claim_id, claim))
        self.emit(claim_id, section, claim)
        return LineOutcome("emitted", claim_id=claim_id)

    def open_slots(self, section: str) -> int:
        return SECTION_LIMIT - len(self.emitted[section])

    def take_failed(self) -> list[dict]:
        """Move pending failures out (they are being replaced on this follow-up call)."""
        taken, self.failed = self.failed, []
        self.dropped_history.extend(taken)
        return taken

    def dropped_all(self) -> list[dict]:
        """Every failed line from every pass — never shown to the producer."""
        return self.dropped_history + self.failed

    def emitted_claims(self, section: str) -> list[Claim]:
        return [c for _, c in self.emitted[section]]

    @property
    def missing(self) -> list[str]:
        return [s for s in SECTIONS if not self.emitted[s]]

    @property
    def evidence_level(self) -> str:
        return "limited" if self.missing else "full"


# --- The pass/follow-up orchestration --------------------------------------------

@dataclass
class Followup:
    """What the writer is told on a follow-up call: what failed and what is already shown."""

    failed_lines: list[dict] = field(default_factory=list)  # {"line", "reasons"}
    emitted: dict[str, list[Claim]] = field(default_factory=dict)
    open_slots: dict[str, int] = field(default_factory=dict)


@dataclass
class RespondResult:
    """Exactly what was shown: the emitted claims, plus what it took to get them."""

    insights: list[Claim]
    peer_examples: list[Claim]
    missing: list[str]
    attempts: int
    dropped: list[dict]  # every failed line with its reasons
    interrupted: bool = False  # a later model failure; emitted claims are still kept

    @property
    def evidence_level(self) -> str:
        return "limited" if self.missing else "full"


def run_respond(writer_fn: Callable[[Followup | None], list[str]], evidence: SessionEvidence,
                standards: Standards, emit: EmitFn,
                check: Callable[[Claim, str], list[str]] | None = None) -> RespondResult:
    """First pass, then up to MAX_FOLLOWUPS follow-ups asking only for open slots.

    `writer_fn(None)` yields the first pass lines; on follow-ups it yields lines again.
    If a follow-up call raises, the claims already emitted are kept as the stored answer
    ([#18 spec](../specs/18-grounded-response.md)); the caller (or #13's `retry_answer`)
    decides what happens next.
    """
    w = GroundedResponseWriter(evidence, standards, emit, check)
    attempts = 1  # counts calls made: first pass + each follow-up actually run
    try:
        for line in writer_fn(None):
            w.feed(line)
        while w.failed and attempts <= MAX_FOLLOWUPS:
            followup = Followup(
                failed_lines=w.take_failed(),
                emitted={s: w.emitted_claims(s) for s in SECTIONS},
                open_slots={s: w.open_slots(s) for s in SECTIONS},
            )
            if not any(v > 0 for v in followup.open_slots.values()):
                break  # both sections full: nothing to ask for
            attempts += 1
            for line in writer_fn(followup):
                w.feed(line)
    except Exception:  # noqa: BLE001 - model/tool failure keeps what was emitted
        return _result(w, attempts, interrupted=True)
    return _result(w, attempts)


def _result(w: GroundedResponseWriter, attempts: int, interrupted: bool = False) -> RespondResult:
    return RespondResult(
        insights=w.emitted_claims("insights"),
        peer_examples=w.emitted_claims("peer_examples"),
        missing=w.missing,
        attempts=attempts,
        dropped=w.dropped_all(),  # failed lines never shown; their reasons explain why
        interrupted=interrupted,
    )


# --- Prompt ----------------------------------------------------------------------

PROMPT_RULES = (
    "Cite only `source` labels and clause IDs exactly as returned by the tools.\n"
    "Use the producer's own history where relevant.\n"
    "No directive language: inform the decision, never direct it. Say nothing about "
    "what the producer should decide.\n"
    "Write one JSON object per line: {\"section\": \"insights\" | \"peer_examples\", "
    "\"claim\": {\"text\": ..., \"citation\": {\"source\", \"standard_clause\"}}}. "
    "One or two plain sentences per claim, in the language below."
)


def respond_prompt(playback: str, profile: list[str], tool_items: list, language: str,
                   followup: Followup | None = None) -> str:
    """Build the respond prompt: playback, profile, tool items, language, rules.

    On follow-up calls the failed lines carry their reason codes and the already
    emitted claims are marked 'already shown, do not repeat' ([#18 spec]).
    """
    items = "\n".join(json.dumps(item, ensure_ascii=False) for item in tool_items)
    parts = [
        "Task: write the grounded answer from these tool results.",
        f"Confirmed playback:\n{playback}",
        "Producer profile:\n" + "\n".join(profile),
        f"Conversation language: {language}",
        "Tool results:\n" + items,
        "Rules:\n" + PROMPT_RULES,
    ]
    if followup is not None:
        shown = {s: [c.text for c in followup.emitted.get(s, [])] for s in SECTIONS}
        parts.append(
            f"Already shown, do not repeat: {json.dumps(shown, ensure_ascii=False)}\n"
            f"Open slots: {json.dumps(followup.open_slots)}. "
            "Ask for no more claims than the open slots.\n"
            "These lines failed; replace them or leave the slots empty:\n"
            + json.dumps(followup.failed_lines, ensure_ascii=False)
        )
    return "\n\n".join(parts)


# --- Fixed text ([#13 spec](13-conversation-steps.md)) ----------------------------

FIXED_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "opening": "Here is what the data shows, and what other producers have tried.",
        "limited_insights": "I don't have solid regional data for your situation yet.",
        "limited_peer_examples": "I don't have examples from comparable producers for this yet.",
        "closing": "You and your committee know your situation best.",
    },
    "es": {
        "opening": "Esto es lo que muestran los datos, y lo que otros productores han probado.",
        "limited_insights": "Todavía no tengo datos regionales sólidos para tu situación.",
        "limited_peer_examples": "Todavía no tengo ejemplos de productores comparables para esto.",
        "closing": "Ustedes y su comité conocen su situación mejor que nadie.",
    },
}


def fixed_text(language: str) -> dict[str, str]:
    """Fixed opening, limited-evidence notices and closing hand-back, in the conversation language."""
    return FIXED_TEXT.get(language) or FIXED_TEXT["en"]