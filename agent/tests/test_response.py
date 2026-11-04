"""Issue #18: grounded response pipeline (seam 1, scripted model output).

Covers the spec's testing list: parse-then-emit, malformed lines, limits, duplicates,
follow-ups for open slots only, immutability of emitted claims, mid-failure keeping
what was shown, fixed text, and prompt construction.
"""
import json

import pytest
from fx_data.standards import Standards

from fex.models import Claim
from fex.response import (
    SECTION_LIMIT,
    ClaimLine,
    Followup,
    GroundedResponseWriter,
    fixed_text,
    normalize,
    parse_claim_line,
    respond_prompt,
    run_respond,
)
from fex.verifier import SessionEvidence

CHIRPS = "CHIRPS rainfall (Cauca, 2024-2025)"
PEER = "FTUSA Premium project record P-0042"
GOOD_CLAUSE = "APS 3.6.1"
GOOD_INSIGHT = ("insights", "Rainfall was 22% below average.", CHIRPS, GOOD_CLAUSE)


@pytest.fixture(scope="module")
def standards():
    return Standards.load()


@pytest.fixture
def evidence():
    ev = SessionEvidence()
    ev.record(CHIRPS, "regional")
    ev.record(PEER, "peer")
    ev.record_clause(GOOD_CLAUSE)  # the verifier now requires the cited clause to have been retrieved
    return ev


def line(section, text, source, clause):
    return json.dumps({"section": section,
                       "claim": {"text": text, "citation": {"source": source, "standard_clause": clause}}},
                      ensure_ascii=False)


class ScriptedWriter:
    """The large model, scripted: one list of lines per call (None first, then Followup)."""

    def __init__(self, *passes):
        self.passes = list(passes)
        self.calls = []

    def __call__(self, followup):
        self.calls.append(followup)
        return self.passes[min(len(self.calls), len(self.passes)) - 1]


def emit_recorder():
    seen = []
    return seen, lambda claim_id, section, claim: seen.append((claim_id, section, claim.text))


# --- Parser and writer ----------------------------------------------------------

def test_blank_line_is_ignored(evidence, standards):
    seen, emit = emit_recorder()
    w = GroundedResponseWriter(evidence, standards, emit)
    assert w.feed("").status == "ignored" and not seen


def test_passing_line_is_parsed_and_emitted_once(evidence, standards):
    seen, emit = emit_recorder()
    w = GroundedResponseWriter(evidence, standards, emit)
    outcome = w.feed(line(*GOOD_INSIGHT))
    assert outcome.status == "emitted" and outcome.claim_id == 1
    assert seen == [(1, "insights", GOOD_INSIGHT[1])]
    assert w.evidence_level == "limited"  # no peer example yet


def test_malformed_line_is_a_failed_claim(evidence, standards):
    seen, emit = emit_recorder()
    w = GroundedResponseWriter(evidence, standards, emit)
    assert w.feed("not json at all").status == "failed"
    assert w.feed('{"section": "insights", "claim": {"text": "x"}}').status == "failed"
    assert w.feed('{"section": "nope", "claim": {}}').status == "failed"
    assert not seen
    for outcome in w.failed:
        assert outcome["reasons"] == ["malformed"]


def test_unverifiable_source_fails_but_a_later_rewrite_is_emitted(evidence, standards):
    seen, emit = emit_recorder()
    w = GroundedResponseWriter(evidence, standards, emit)
    invented = ("insights", "Prices will double.", "Made-up forecast", GOOD_CLAUSE)
    assert w.feed(line(*invented)).status == "failed"
    assert "Made-up forecast" in w.failed[0]["reasons"][0]
    assert w.feed(line(*GOOD_INSIGHT)).status == "emitted"
    assert [text for _, _, text in seen] == [GOOD_INSIGHT[1]]


def test_limits_ignores_a_fourth_insight(evidence, standards):
    seen, emit = emit_recorder()
    w = GroundedResponseWriter(evidence, standards, emit)
    for i in range(SECTION_LIMIT + 1):
        w.feed(line("insights", f"Insight number {i}.", CHIRPS, GOOD_CLAUSE))
    assert len(w.emitted_claims("insights")) == SECTION_LIMIT and w.overflow == 1
    assert len(seen) == SECTION_LIMIT


def test_duplicate_line_is_dropped(evidence, standards):
    seen, emit = emit_recorder()
    w = GroundedResponseWriter(evidence, standards, emit)
    w.feed(line(*GOOD_INSIGHT))
    assert w.feed(line(*GOOD_INSIGHT)).status == "duplicate"
    assert w.feed(line("insights", "  rainfall was  22% BELOW  average.", CHIRPS, GOOD_CLAUSE)).status == "duplicate"
    assert len(seen) == 1 and w.duplicates == 2


# --- Orchestration ------------------------------------------------------------

def test_followup_receives_failed_lines_and_emitted(evidence, standards):
    seen, emit = emit_recorder()
    invented = ("insights", "Prices will double.", "Made-up forecast", GOOD_CLAUSE)
    fixed = ("insights", "Prices for your coffee went up last season.", CHIRPS, GOOD_CLAUSE)
    peer = ("peer_examples", "A cooperative funded rainwater catchment.", PEER, GOOD_CLAUSE)
    writer = ScriptedWriter(
        [line(*GOOD_INSIGHT), line(*invented)],
        [line(*GOOD_INSIGHT), line(*fixed), line(*peer)],  # repeats shown claim, fixes the slot, adds peer
    )
    result = run_respond(writer, evidence, standards, emit)

    assert writer.calls[0] is None
    followup = writer.calls[1]
    assert isinstance(followup, Followup)
    assert followup.open_slots == {"insights": 2, "peer_examples": 3}
    assert len(followup.failed_lines) == 1
    assert "Made-up forecast" in followup.failed_lines[0]["reasons"][0]
    assert [c.text for c in followup.emitted["insights"]] == [GOOD_INSIGHT[1]]

    assert result.attempts == 2  # the repeated claim was dropped; the two passing lines emitted
    assert [text for _, _, text in seen] == [GOOD_INSIGHT[1], fixed[1], peer[1]]
    assert [c.text for c in result.insights] == [GOOD_INSIGHT[1], fixed[1]]
    assert [c.text for c in result.peer_examples] == [peer[1]]
    assert result.evidence_level == "full"


def test_no_followup_when_both_sections_are_full(evidence, standards):
    seen, emit = emit_recorder()
    writer = ScriptedWriter([line(s, f"Claim {i}.", CHIRPS if s == "insights" else PEER, GOOD_CLAUSE)
                             for s in ("insights", "peer_examples") for i in range(SECTION_LIMIT)])
    result = run_respond(writer, evidence, standards, emit)
    assert writer.calls == [None] and result.attempts == 1
    assert result.evidence_level == "full"


def test_gives_up_after_two_followups(evidence, standards):
    seen, emit = emit_recorder()
    writer = ScriptedWriter([line("insights", "Bad.", "Nowhere", GOOD_CLAUSE)],
                            [line("insights", "Bad.", "Elsewhere", GOOD_CLAUSE)],
                            [line("insights", "Bad.", "Anywhere", GOOD_CLAUSE)])
    result = run_respond(writer, evidence, standards, emit)
    assert result.attempts == 3  # first pass + 2 follow-ups, then stop
    assert result.insights == []


def test_failure_partway_keeps_the_emitted_claims(evidence, standards):
    seen, emit = emit_recorder()

    def broken(followup):
        if followup is None:
            return [line(*GOOD_INSIGHT), line("insights", "Bad claim.", "Nowhere", GOOD_CLAUSE)]
        raise RuntimeError("model call failed halfway through")

    result = run_respond(broken, evidence, standards, emit)
    assert result.interrupted is True and result.attempts == 2  # first pass + the broken follow-up
    assert [c.text for c in result.insights] == [GOOD_INSIGHT[1]]
    assert len(seen) == 1  # what the producer saw is kept


def test_failed_emission_is_neither_shown_nor_tracked(evidence, standards):
    """A raising emission callback must leave the claim unshown and untracked.

    The interrupted result then has stored == shown, and the same identity fed
    again later is a fresh claim, not a dropped duplicate.
    """
    calls = []
    emissions = {"count": 0}

    def emit_once_fails(claim_id, section, claim):
        emissions["count"] += 1
        if emissions["count"] == 1:
            raise RuntimeError("event queue unavailable")
        calls.append((claim_id, section, claim.text))

    w = GroundedResponseWriter(evidence, standards, emit_once_fails)
    with pytest.raises(RuntimeError):
        w.feed(line("insights", "Undelivered.", CHIRPS, GOOD_CLAUSE))
    assert w.emitted_claims("insights") == []

    out = w.feed(line(*GOOD_INSIGHT))
    assert out.status == "emitted" and out.claim_id == 1

    retry = w.feed(line("insights", "Undelivered.", CHIRPS, GOOD_CLAUSE))
    assert retry.status == "emitted" and retry.claim_id == 2
    assert [t for _, _, t in calls] == [GOOD_INSIGHT[1], "Undelivered."]


def test_run_respond_keeps_stored_equal_to_shown_when_emission_fails(evidence, standards):
    seen = []

    def flaky(claim_id, section, claim):
        if claim.text != GOOD_INSIGHT[1]:
            raise RuntimeError("event queue unavailable")
        seen.append((claim_id, section, claim.text))

    def writer(followup):
        return [line(*GOOD_INSIGHT), line("insights", "Undelivered.", CHIRPS, GOOD_CLAUSE)]

    result = run_respond(writer, evidence, standards, flaky)
    assert result.interrupted is True
    assert [c.text for c in result.insights] == [GOOD_INSIGHT[1]]  # stored == shown
    assert len(seen) == 1


# --- Fixed text and prompt ------------------------------------------------------

def test_fixed_text_in_both_languages():
    for lang in ("en", "es"):
        text = fixed_text(lang)
        assert set(text) >= {"opening", "limited_insights", "limited_peer_examples", "closing"}
    assert "committee" in fixed_text("en")["closing"] and "comité" in fixed_text("es")["closing"]
    assert fixed_text("pt") == fixed_text("en")  # unknown language falls back to English


def test_prompt_carries_playback_profile_tools_and_rules():
    prompt = respond_prompt(
        playback="El productor pregunta por la lluvia.",
        profile=["Crop: coffee", "Region: Cauca, Colombia"],
        tool_items=[{"source": CHIRPS, "rows": [{"rain_mm": 900}]}],
        language="es",
    )
    assert "El productor pregunta por la lluvia." in prompt
    assert "Crop: coffee" in prompt
    assert CHIRPS in prompt  # tool results, source label verbatim
    assert "es" in prompt
    assert "one JSON object per line" in prompt and "never direct it" in prompt


def test_followup_prompt_marks_emitted_and_failed_lines():
    followup = Followup(
        failed_lines=[{"line": "bad", "reasons": ["malformed"]}],
        emitted={"insights": [Claim.model_validate({"text": "Shown already.",
                                                    "citation": {"source": CHIRPS, "standard_clause": GOOD_CLAUSE}})],
                 "peer_examples": []},
        open_slots={"insights": 2, "peer_examples": 3},
    )
    prompt = respond_prompt("pb", ["p"], [], "es", followup)
    assert "Already shown, do not repeat" in prompt
    assert "Shown already." in prompt and "malformed" in prompt
    assert "Open slots" in prompt and '{"insights": 2, "peer_examples": 3}' in prompt


def test_parse_helpers():
    parsed = parse_claim_line(line(*GOOD_INSIGHT))
    assert isinstance(parsed, ClaimLine) and parsed.section == "insights"
    assert normalize("  La  LLUVIA  fue  baja. ") == "la lluvia fue baja."
    with pytest.raises(ValueError):
        parse_claim_line('[{"section": "insights"}]')