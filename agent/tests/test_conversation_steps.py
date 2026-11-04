"""Issue #13: conversation steps, driven through the agent entrypoint (spec seam 1).

Spec: docs/specs/13-conversation-steps.md. One test per case in its "Testing Decisions".
"""
from dataclasses import replace

import pytest
from fx_data.peers import PeerProjects, ProducerProfiles
from tests.conversation_harness import (
    RETRIEVE, Run, allowed, answer, cauca_producer, claim, intake, last_step, of, playback, short_reply, summary, types,
)
from tests.tool_harness import call_tool

from fex.tools.peer_examples import find_peer_examples
from fex.tools.regional_context import get_regional_context

STEPS = ["intake", "playback", "respond", "consent", "feedback", "closed"]
ACTIONS = {
    "confirm_playback": {}, "correct_playback": {"text": "No, fue granizo."}, "reopen_playback": {},
    "retry_answer": {}, "set_consent": {"scope": "internal"}, "set_feedback": {"value": "yes"}, "end": {},
}
VALID_IN = {
    "intake": {"end"},
    "playback": {"confirm_playback", "correct_playback", "end"},
    "respond": {"reopen_playback", "retry_answer", "end"},  # respond is only held after an error
    "consent": {"reopen_playback", "set_consent", "end"},
    "feedback": {"reopen_playback", "set_consent", "set_feedback", "end"},
    "closed": set(),
}


def run_in(step: str) -> Run:
    """A conversation sitting in `step`."""
    r = Run()
    if step == "intake":
        r.small.add(intake("¿Qué ha sido difícil?"))
        r.send("start")
    elif step == "playback":
        r.to_playback()
    elif step == "respond":  # an answer that failed: respond is held until retry
        r.to_playback()
        r.small.add(summary())
        r.large.add(("raise", RuntimeError("bedrock down")))
        r.action("confirm_playback")
    elif step == "consent":
        r.to_consent()
    elif step == "feedback":
        r.to_feedback()
    elif step == "closed":
        r.to_consent()
        r.action("end")
    assert r.state().step == step
    return r


# ---------------------------------------------------------------- step transitions

def test_start_asks_an_open_question_in_intake():
    r = Run()
    r.small.add(intake("¿Qué ha sido lo más difícil este año?"))
    events = r.send("start")
    assert last_step(events) == "intake"
    assert "".join(e.text for e in of(events, "text")) == "¿Qué ha sido lo más difícil este año?"
    assert allowed(events) == ["end"]
    assert types(events)[-1] == "done"
    assert [e.seq for e in events] == list(range(1, len(events) + 1))


def test_start_loads_the_profile_from_the_request_producer():
    r = Run()
    r.small.add(intake("Hola"))
    r.send("start")
    profile = r.state().profile
    assert profile.producer_id == r.producer_id and profile.region == "Cauca"


def test_intake_follow_ups_stay_in_intake_until_the_model_is_ready():
    r = Run()
    r.small.add(intake("¿Qué ha sido difícil?"), intake("¿Desde cuándo?"))
    r.send("start")
    events = r.send("message", text="La lluvia.")
    assert r.state().step == "intake"
    assert "¿Desde cuándo?" in "".join(e.text for e in of(events, "text"))


def test_ready_intake_moves_to_playback_with_buttons():
    events = Run().to_playback()
    assert last_step(events) == "playback"
    assert set(allowed(events)) == {"confirm_playback", "correct_playback", "end"}
    assert "la lluvia bajó" in "".join(e.text for e in of(events, "text"))


def test_confirm_runs_retrieval_then_streams_verified_claims_and_moves_to_consent():
    r = Run()
    events = r.to_consent()
    assert of(events, "step")[0].step == "respond" and last_step(events) == "consent"
    claims = of(events, "claim")
    assert [c.section for c in claims] == ["insights", "peer_examples"]
    final = of(events, "answer")[0]
    assert final.evidence == "full" and len(final.insights) == 1 and len(final.peer_examples) == 1
    assert types(events).index("claim") < types(events).index("answer")


def test_confirm_generates_summaries_and_tags_from_the_confirmed_playback():
    r = Run()
    r.to_consent()
    pb = r.state().playback
    assert pb.tags == ["water", "climate and weather"]
    assert pb.summary_original == "La lluvia bajó." and pb.summary_english == "Rain fell."


def test_granted_consent_moves_to_feedback_and_declined_stays():
    r = Run()
    r.to_consent()
    assert last_step(r.action("set_consent", scope="declined")) == "consent"
    assert last_step(r.action("set_consent", scope="internal_and_outward")) == "feedback"
    assert r.state().consent == "internal_and_outward"


def test_changing_to_declined_from_feedback_returns_to_consent_and_clears_feedback():
    r = Run()
    r.to_feedback()
    r.action("set_feedback", value="yes")
    events = r.action("set_consent", scope="declined")
    assert last_step(events) == "consent"
    assert r.state().feedback is None and r.state().consent == "declined"


def test_feedback_is_recorded_and_replaceable():
    r = Run()
    r.to_feedback()
    r.action("set_feedback", value="somewhat")
    r.action("set_feedback", value="yes")
    assert r.state().feedback == "yes" and r.state().step == "feedback"


@pytest.mark.parametrize("step", STEPS)
@pytest.mark.parametrize("name", list(ACTIONS))
def test_every_invalid_action_is_rejected_in_every_step(step, name):
    if name in VALID_IN[step]:
        pytest.skip("valid here")
    r = run_in(step)
    before = r.state().model_dump()
    events = r.action(name, **ACTIONS[name])
    errors = of(events, "error")
    assert errors and errors[0].code == ("closed" if step == "closed" else "invalid_action")
    assert r.state().model_dump() == before


# ---------------------------------------------------------------- tool gating

@pytest.mark.parametrize("step", ["intake", "playback", "consent", "feedback", "closed", None])
@pytest.mark.parametrize("tool,args", [(get_regional_context, {}), (find_peer_examples, {"challenge": "water"})])
def test_data_tools_refuse_outside_respond(step, tool, args):
    state = {"producer_id": cauca_producer(), "step": step}  # step=None sends no step at all
    status, result = call_tool(tool, args, state)
    assert status == "success"
    assert result == {"refused": True, "reason": "Data tools run only after the producer confirms the playback."}


def test_the_engine_only_offers_data_tools_in_respond():
    r = Run()
    r.to_consent()
    data_tools = {"get_regional_context", "find_peer_examples"}
    small_offered = {name for call in r.small.calls for name in call}
    assert not small_offered & data_tools
    assert data_tools <= {name for call in r.large.calls for name in call}


# ---------------------------------------------------------------- typed text outside intake/playback

@pytest.mark.parametrize("step", ["consent", "feedback"])
def test_typed_text_in_consent_or_feedback_changes_nothing(step):
    r = run_in(step)
    r.small.add(short_reply("Compartido significa resumido para socios."))
    before, large_calls = r.state(), len(r.large.calls)
    events = r.send("message", text="sí, guárdelo todo y compártalo")
    after = r.state()
    assert (after.step, after.consent, after.feedback) == (before.step, before.consent, before.feedback)
    assert "Compartido" in "".join(e.text for e in of(events, "text"))
    assert len(r.large.calls) == large_calls  # no answer, no data tools


def test_typed_text_never_offers_data_tools():
    r = run_in("consent")
    r.small.add(short_reply())
    r.send("message", text="¿y el clima?")
    assert all("get_regional_context" not in call for call in r.small.calls)


# ---------------------------------------------------------------- corrections

def test_correct_playback_action_reruns_playback():
    r = Run()
    r.to_playback()
    r.small.add(playback("Entiendo: fue granizo, no sequía."))
    events = r.action("correct_playback", text="No, fue granizo.")
    assert last_step(events) == "playback"
    assert "granizo" in "".join(e.text for e in of(events, "text"))
    assert r.state().playback.text == "Entiendo: fue granizo, no sequía."


def test_typed_text_in_playback_is_a_correction():
    r = Run()
    r.to_playback()
    r.small.add(playback("Entiendo: fue granizo."))
    r.send("message", text="Fue granizo")
    assert r.state().step == "playback" and "granizo" in r.state().playback.text


def test_entity_type_correction_is_kept_and_used_for_peer_matching():
    r = Run()
    r.small.add(intake("Hola"), intake("", ready=True), playback(entity_type="estate"))
    r.send("start")
    r.send("message", text="Somos una finca, no una cooperativa.")
    assert r.state().entity_type == "estate"
    profile = ProducerProfiles.load().get(r.producer_id)
    status, peers = call_tool(find_peer_examples, {"challenge": "water"},
                              {"producer_id": r.producer_id, "step": "respond", "entity_type": "estate"})
    assert status == "success" and peers
    projects = {p["project_ref"]: p for p in PeerProjects.load()._projects}
    corrected = replace(profile, entity_type="estate")
    assert [p["match_score"] for p in peers] == [PeerProjects.score(projects[p["project_ref"]], corrected) for p in peers]


def test_disputed_location_is_noted_and_the_location_on_file_is_kept():
    r = Run()
    r.small.add(intake("Hola"), intake("", ready=True), playback(location_disputed=True))
    r.send("start")
    events = r.send("message", text="No estamos en Cauca.")
    assert r.state().location_note
    assert "Cauca" in "".join(e.text for e in of(events, "text"))  # tells them it uses the location on file
    assert r.state().profile.region == "Cauca"


# ---------------------------------------------------------------- reopen

@pytest.mark.parametrize("step", ["consent", "feedback"])
def test_reopen_clears_consent_and_feedback_and_keeps_the_old_answer(step):
    r = run_in(step)
    if step == "feedback":
        r.action("set_feedback", value="no")
    events = r.action("reopen_playback")
    s = r.state()
    assert last_step(events) == "playback"
    assert s.consent is None and s.feedback is None and s.answer is None
    assert [a.reason for a in s.earlier_answers] == ["reopened"]
    # confirming again produces a new answer
    r.small.add(summary())
    r.large.add(*RETRIEVE, r.good_answer())
    assert last_step(r.action("confirm_playback")) == "consent"
    assert r.state().answer is not None


# ---------------------------------------------------------------- verification

def test_a_failing_claim_is_never_emitted_and_a_passing_rewrite_is():
    r = Run()
    r.to_playback()
    r.small.add(summary())
    invented = claim("Invented rainfall.", "Made-up source")
    fixed = claim("Rainfall fell.", r.regional[0]["source"])
    r.large.add(*RETRIEVE, answer([invented], [claim("Peer.", r.peers[0]["source"])]), answer([fixed], []))
    events = r.action("confirm_playback")
    shown = [c.claim.text for c in of(events, "claim")]
    assert "Invented rainfall." not in shown
    assert shown == ["Peer.", "Rainfall fell."] or shown == ["Rainfall fell.", "Peer."]
    assert of(events, "answer")[0].evidence == "full"


def test_claims_that_never_pass_are_dropped():
    r = Run()
    r.to_playback()
    r.small.add(summary())
    bad = claim("Invented.", "Made-up source")
    r.large.add(*RETRIEVE, answer([bad], [claim("Peer.", r.peers[0]["source"])]), answer([bad], []), answer([bad], []))
    events = r.action("confirm_playback")
    assert [c.claim.text for c in of(events, "claim")] == ["Peer."]


def test_a_claim_citing_a_fake_clause_is_never_emitted():
    r = Run()
    r.to_playback()
    r.small.add(summary())
    fake_clause = claim("Rain.", r.regional[0]["source"], clause="APS 99.99")
    r.large.add(*RETRIEVE, answer([fake_clause], [claim("Peer.", r.peers[0]["source"])]),
                answer([fake_clause], []), answer([fake_clause], []))
    assert "Rain." not in [c.claim.text for c in of(r.action("confirm_playback"), "claim")]


def test_no_verified_insights_gives_the_limited_evidence_notice_and_moves_on():
    r = Run()
    r.to_playback()
    r.small.add(summary())
    r.large.add(*RETRIEVE, answer([], [claim("Peer.", r.peers[0]["source"])]))
    events = r.action("confirm_playback")
    final = of(events, "answer")[0]
    assert final.evidence == "limited" and final.insights == []
    assert "todavía no tengo datos" in "".join(e.text for e in of(events, "text")).lower()
    assert last_step(events) == "consent"


def test_respond_text_is_only_fixed_copy_and_checked_claims():
    r = Run()
    events = r.to_consent()
    respond_text = "".join(e.text for e in of(events, "text"))
    assert "usted y su comité conocen mejor su situación" in respond_text.lower()


# ---------------------------------------------------------------- failure and retry

def test_failure_after_a_claim_then_retry_keeps_shown_claims_as_interrupted():
    r = Run()
    r.to_playback()
    r.small.add(summary())
    bad = claim("Invented.", "Made-up source")
    good_peer = claim("Peer.", r.peers[0]["source"])
    # first attempt: one claim passes and is shown, the rewrite call fails
    r.large.add(*RETRIEVE, answer([bad], [good_peer]), ("raise", RuntimeError("throttled")))
    events = r.action("confirm_playback")
    assert [c.claim.text for c in of(events, "claim")] == ["Peer."]
    assert of(events, "error")[0].code == "agent_failed"
    assert r.state().step == "respond" and "retry_answer" in allowed(events)

    r.large.add(*RETRIEVE, r.good_answer())
    events = r.action("retry_answer")
    assert last_step(events) == "consent"
    earlier = r.state().earlier_answers
    assert [a.reason for a in earlier] == ["interrupted"]
    assert [c.text for c in earlier[0].peer_examples] == ["Peer."]


# ---------------------------------------------------------------- closing

@pytest.mark.parametrize("step", STEPS[:-1])
def test_end_closes_from_every_open_step(step):
    r = run_in(step)
    events = r.action("end")
    assert last_step(events) == "closed" and allowed(events) == []


@pytest.mark.parametrize("reason", ["inactivity", "max_lifetime"])
@pytest.mark.parametrize("step", STEPS[:-1])
def test_auto_close_closes_from_every_open_step(step, reason):
    r = run_in(step)
    events = r.send("auto_close", reason=reason)
    assert last_step(events) == "closed"
    assert r.state().closed_reason == reason


def test_end_keeps_the_latest_consent_and_feedback():
    r = Run()
    r.to_feedback()
    r.action("set_feedback", value="somewhat")
    r.action("end")
    s = r.state()
    assert (s.step, s.consent, s.feedback) == ("closed", "internal", "somewhat")


def test_nothing_changes_once_closed():
    r = run_in("closed")
    before = r.state().model_dump()
    events = r.send("message", text="hola")
    assert of(events, "error")[0].code == "closed"
    assert r.state().model_dump() == before


# ---------------------------------------------------------------- repeated actions, history, resume

def test_repeated_identical_actions_add_no_history():
    r = Run()
    r.to_feedback()
    n = len(r.state().history)
    r.action("set_consent", scope="internal")
    r.action("set_feedback", value="yes")
    r.action("set_feedback", value="yes")
    s = r.state()
    assert len(s.history) == n + 1
    assert [c.scope for c in s.consent_history] == ["internal"]


def test_consent_history_records_each_distinct_choice():
    r = Run()
    r.to_consent()
    r.action("set_consent", scope="declined")
    r.action("set_consent", scope="internal")
    r.action("set_consent", scope="internal")
    assert [c.scope for c in r.state().consent_history] == ["declined", "internal"]


def test_resume_returns_step_allowed_actions_answer_and_history():
    r = Run()
    r.to_consent()
    resumed = r.send("resume")
    assert resumed.step == "consent"
    assert set(resumed.allowed) == VALID_IN["consent"]
    assert resumed.answer is not None and resumed.answer.evidence == "full"
    roles = [h.role for h in resumed.history]
    assert roles[0] == "fex" and "producer" in roles and "action" in roles


def test_actions_and_requests_never_take_ids_from_the_payload_body():
    r = Run()
    r.small.add(intake("Hola"))
    r.send("start")
    with pytest.raises(ValueError):
        r.engine.handle({"kind": "action", "producerId": r.producer_id, "conversationId": "conv-1",
                         "action": {"name": "set_consent", "args": {"scope": "internal", "producer_id": "P-999"}}})


def test_state_is_rebuilt_from_the_store_on_every_request():
    r = Run()
    r.to_playback()
    stored = r.store.raw(r.producer_id, r.conversation_id)
    assert isinstance(stored, str) and '"step":"playback"' in stored.replace(" ", "")


def test_conversations_are_scoped_to_the_requesting_producer():
    r = Run()
    r.to_playback()
    # the same conversation ID under another producer is a different (unknown) conversation
    other = r.engine.handle({"kind": "message", "text": "hola", "producerId": "SOMEONE-ELSE",
                             "conversationId": r.conversation_id})
    assert of(other, "error")[0].code == "invalid_action"
    assert r.store.load("SOMEONE-ELSE", r.conversation_id) is None


# ---------------------------------------------------------------- review fixes (Codex on #67)

def test_entity_type_can_be_corrected_back_to_the_value_on_file():
    r = Run()
    r.small.add(intake("Hola"), intake("", ready=True), playback(entity_type="estate"))
    r.send("start")
    r.send("message", text="Somos una finca.")
    on_file = r.state().profile.entity_type
    assert r.state().effective_entity_type == "estate"
    r.small.add(playback(entity_type=on_file))
    r.action("correct_playback", text=f"Perdón, sí somos {on_file}.")
    assert r.state().effective_entity_type == on_file
    assert r.state().entity_type is None  # back to the profile value: no override left


def test_a_failing_data_tool_is_an_answer_failure_with_retry():
    r = Run()
    r.to_playback()
    r.small.add(summary())
    # an invalid tool input makes Strands return a toolResult with status "error" (no exception raised)
    # The answer needs no rewrite, so only the tool error can make this fail
    r.large.add(("tool", "find_peer_examples", {"challenge": "not-a-tag"}), answer([], []))
    events = r.action("confirm_playback")
    assert of(events, "error")[0].code == "agent_failed"
    assert of(events, "claim") == [] and of(events, "answer") == []
    assert r.state().step == "respond" and "retry_answer" in allowed(events)


def test_follow_up_questions_see_the_answer_that_was_shown():
    r = Run()
    r.to_consent()
    r.small.add(short_reply("Es un ejemplo de otra cooperativa."))
    r.send("message", text="¿Qué significa el ejemplo que mostró?")
    prompt = r.small.prompts[-1]
    assert "Rainfall fell." in prompt and "A peer built tanks." in prompt
