"""The eval harness (#36): evaluators, the scenario runner, the AgentCore invoker, distinctness and the report.

Fixture sessions come from real demo-model runs (no AWS), then get their claims or evidence edited to make
each case. The judge is a stub; the Bedrock judge is tested against a stub client.
"""
import json
from datetime import UTC, datetime

import pytest
from fex.eval_evidence import AnswerEvidence, EvalEvidence, ShownClaim
from fex.models import Citation, Claim
from fx_data.standards import Standards
from fx_evals import evaluators as ev
from fx_evals.distinctness import pair_rows
from fx_evals.judge import BedrockJudge, JudgeError
from fx_evals.offline import run_all
from fx_evals.report import judge_calibrated, markdown, score
from fx_evals.runner import AgentCoreInvoker, ScenarioRunner, agentcore_dataset
from fx_evals.runs import LAST_REPLY, PAIR_RUNS, Run, all_runs, contrast_pairs, labeled_runs, scenario_runs
from fx_evals.session import session_id_from_payload

RUNS = {r.run_id: r for r in all_runs()}
STANDARDS = Standards.load()
NOW = datetime(2026, 11, 5, tzinfo=UTC)


@pytest.fixture(scope="module")
def sessions(tmp_path_factory):
    picked = [RUNS[i] for i in ("S1", "S4", "S7", "C4-SYN-008", "L01")]
    return {s.run.run_id: s for s in run_all(picked, tmp_path_factory.mktemp("records"), demo=True)}


def with_claims(session, claims: list[tuple[str, str, str, str]]):
    """The session with one answer whose shown claims are (section, text, source, clause)."""
    shown = [ShownClaim(section=sec, claim=Claim(text=text, citation=Citation(source=src, standard_clause=cl)))
             for sec, text, src, cl in claims]
    items = [i for a in session.evidence.answers for i in a.tool_results]
    evidence = session.evidence.model_copy(update={"answers": [AnswerEvidence(started_at=NOW, tool_results=items,
                                                                              claims=shown)]})
    return type(session)(run=session.run, conversation_id=session.conversation_id, record=session.record,
                         evidence=evidence)


def item(session, kind):
    return next(i for a in session.evidence.answers for i in a.tool_results if i["kind"] == kind)


def clause(session):
    return item(session, "standard")["data"]["clause_id"]


class StubJudge:
    model_id = "stub-judge"

    def __init__(self, supports=True, tone=5, fail=False):
        self._supports, self._tone, self.fail = supports, tone, fail

    def supports(self, claim, source_text):
        if self.fail:
            raise JudgeError("malformed")
        return (self._supports(claim) if callable(self._supports) else self._supports), "stub"

    def tone(self, text):
        if self.fail:
            raise JudgeError("timed out")
        return self._tone, "stub"


# ------------------------------------------------------------------ evaluators (spec 36 testing decisions)

def test_jaccard_including_empty_sets():
    assert ev.jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert ev.jaccard(set(), {"a"}) == 0.0
    assert ev.jaccard(set(), set()) == 1.0


def test_a_claim_whose_source_is_not_in_the_evidence_fails(sessions):
    s = sessions["S1"]
    fixed = with_claims(s, [("insights", "Rain fell.", item(s, "regional")["source"], clause(s)),
                            ("insights", "Invented.", "A source no tool returned", clause(s))])
    r = ev.citation_validity(fixed, STANDARDS)
    assert r["value"] == 0.5 and r["breakdown"]["problems"][0]["codes"] == ["unknown_source"]


def test_a_peer_example_citing_a_regional_source_fails(sessions):
    s = sessions["S1"]
    fixed = with_claims(s, [("peer_examples", "Peers saw less rain.", item(s, "regional")["source"], clause(s))])
    assert ev.citation_validity(fixed, STANDARDS)["breakdown"]["problems"][0]["codes"] == ["wrong_source_kind"]


def test_citation_validity_is_unscored_without_evidence(sessions):
    s = sessions["S1"]
    s2 = type(s)(run=s.run, conversation_id=s.conversation_id, record=s.record, evidence=None)
    assert ev.citation_validity(s2, STANDARDS)["value"] is None


def test_a_directive_phrase_in_spanish_scores_0(sessions):
    s = sessions["S1"]
    fixed = with_claims(s, [("insights", "Usted debe instalar riego.", item(s, "regional")["source"], clause(s))])
    r = ev.directive_language(fixed)
    assert r["value"] == 0.0 and r["breakdown"]["matches"]


def test_a_leak_fixture_scores_1_and_shared_catalog_ids_score_0(sessions):
    s, own = sessions["S1"], ev.Ownership()
    other_project = next(i for i, owner in own.owner.items() if i.startswith("PRJ-") and owner != s.run.producer_id)
    leaked = with_claims(s, [("insights", f"A neighbour's project {other_project} worked.",
                              item(s, "regional")["source"], clause(s))])
    assert ev.scope_leak(leaked, own)["value"] == 1.0
    assert ev.scope_leak(leaked, own)["breakdown"]["other_producer_ids"] == [other_project]
    peer = item(s, "peer")["source"]  # "Premium project, <org> [CAT-...]": shared by design
    assert "CAT-" in peer and ev.scope_leak(with_claims(s, [("peer_examples", "A peer.", peer, clause(s))]), own)["value"] == 0.0
    assert ev.scope_leak(s, own)["value"] == 0.0, "the producer's own IDs are not a leak"


def test_an_id_the_producer_typed_is_not_a_leak_but_a_private_marker_is(sessions):
    s, own = sessions["S1"], ev.Ownership()
    other = "SYN-SCOPE-B"
    typed = Run(**{**s.run.__dict__, "turns": s.run.turns + [{"message": f"What did {other} do?", "expect_step": "intake"}]})
    fixed = with_claims(s, [("insights", f"About {other}.", item(s, "regional")["source"], clause(s))])
    assert ev.scope_leak(type(s)(run=typed, conversation_id="c", record=s.record, evidence=fixed.evidence), own)["value"] == 0.0
    marked = Run(**{**s.run.__dict__, "private_markers": ["Rainfall near the centre of Cauca"]})
    r = ev.scope_leak(type(s)(run=marked, conversation_id="c", record=s.record, evidence=s.evidence), own)
    assert r["value"] == 1.0 and r["breakdown"]["private_markers"]


def test_claim_support_counts_unsupported_claims_and_a_malformed_reply_leaves_it_unscored(sessions):
    s = sessions["S1"]
    reg = item(s, "regional")["source"]
    fixed = with_claims(s, [("insights", "Supported.", reg, clause(s)), ("insights", "Wrong number.", reg, clause(s)),
                            ("insights", "Unknown.", "nowhere", clause(s))])
    r = ev.claim_support(fixed, StubJudge(supports=lambda c: c != "Wrong number."))
    assert r["value"] == 0.5 and r["breakdown"]["judged"] == 2, "an unknown source is left to citation_validity"
    assert ev.claim_support(fixed, StubJudge(fail=True))["value"] is None
    assert ev.claim_support(fixed, None)["value"] is None


def test_tone_is_the_judges_score_and_unscored_when_the_reply_is_unusable(sessions):
    assert ev.enablement_tone(sessions["S1"], StubJudge(tone=4))["value"] == 4.0
    assert ev.enablement_tone(sessions["S1"], StubJudge(fail=True))["value"] is None


def test_tag_overlap_uses_the_labeled_accounts_reference_tags(sessions):
    s = sessions["L01"]
    r = ev.tag_overlap(s)
    assert r["breakdown"]["reference_tags"] == RUNS["L01"].reference_tags
    assert r["value"] == ev.jaccard(s.record.tags, RUNS["L01"].reference_tags)


# ------------------------------------------------------------------ the Bedrock judge's reply handling

class FakeBedrock:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def test_the_bedrock_judge_reads_json_and_rejects_anything_else():
    good = BedrockJudge(client=FakeBedrock('Here: {"score": 4, "reason": "informs"}'))
    assert good.tone("x") == (4, "informs") and good.model_id == "us.amazon.nova-pro-v1:0"
    assert BedrockJudge(client=FakeBedrock('{"supported": false, "reason": "no"}')).supports("c", "s") == (False, "no")
    for bad in [BedrockJudge(client=FakeBedrock("no json")), BedrockJudge(client=FakeBedrock('{"score": 9}')),
                BedrockJudge(client=FakeBedrock('{"score": true}')), BedrockJudge(client=FakeBedrock("{oops}")),
                BedrockJudge(client=FakeBedrock(error=TimeoutError("read timeout")))]:
        with pytest.raises(JudgeError):
            bad.tone("x")
    with pytest.raises(JudgeError):
        BedrockJudge(client=FakeBedrock('{"supported": "yes"}')).supports("c", "s")


# ------------------------------------------------------------------ session ID from an evaluator payload

def test_the_session_id_comes_from_the_reference_inputs_then_the_spans():
    span = lambda sid: {"attributes": {"session.id": sid}}  # noqa: E731
    assert session_id_from_payload({"evaluationReferenceInputs": [{"context": {"spanContext": {"sessionId": "a"}}}],
                                    "evaluationInput": {"sessionSpans": [span("b")]}}) == "a"
    assert session_id_from_payload({"evaluationInput": {"sessionSpans": [span("b"), span("b"), {"attributes": {}}]}}) == "b"
    for spans in ([], [span("b"), span("c")]):
        with pytest.raises(ValueError):
            session_id_from_payload({"evaluationInput": {"sessionSpans": spans}})


# ------------------------------------------------------------------ the scenario runner

def step(s, allowed):
    return [{"type": "step", "step": s}, {"type": "actions", "allowed": allowed}, {"type": "done"}]


class FakeTransport:
    """Answers each request from a script of event lists and records the requests."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def send(self, producer_id, conversation_id, body):
        self.sent.append(body)
        return iter(self.replies.pop(0) if self.replies else step("intake", ["end"]))


RUN = Run(run_id="R1", kind="scenario", producer_id="SYN-001", language="en",
          turns=[{"message": "Hello.", "expect_step": "playback"},
                 {"action": {"name": "confirm_playback", "args": {}}, "expect_step": "consent"}],
          intake_replies=["More detail."])


def test_a_run_that_reaches_each_step_has_no_problems_and_answers_extra_intake_questions():
    t = FakeTransport(step("intake", ["end"]), step("intake", ["end"]),
                      step("playback", ["confirm_playback", "end"]), step("consent", ["set_consent", "end"]))
    result = ScenarioRunner(t).run(RUN, "c-1")
    assert result.problems == []
    assert t.sent == [{"kind": "start"}, {"kind": "message", "text": "Hello."},
                      {"kind": "message", "text": "More detail."},
                      {"kind": "action", "action": {"name": "confirm_playback", "args": {}}}]


def test_a_stream_that_ends_before_done_is_a_problem():
    cut = [{"type": "step", "step": "intake"}, {"type": "text", "text": "Wh"}]
    result = ScenarioRunner(FakeTransport(step("intake", ["end"]), cut)).run(RUN, "c-1")
    assert any("ended before done" in p for p in result.problems)


def test_an_error_event_is_a_problem():
    err = [{"type": "error", "code": "agent_failed", "message": "boom"}, {"type": "done"}]
    result = ScenarioRunner(FakeTransport(step("intake", ["end"]), err)).run(RUN, "c-1")
    assert any("agent_failed" in p for p in result.problems)


def test_an_action_that_is_not_allowed_fails_without_being_sent():
    t = FakeTransport(step("intake", ["end"]), step("playback", ["end"]))
    result = ScenarioRunner(t).run(RUN, "c-1")
    assert "confirm_playback is not allowed" in result.problems[0] and len(t.sent) == 2


def test_running_out_of_intake_replies_sends_the_last_reply_then_gives_up():
    t = FakeTransport()  # always intake
    result = ScenarioRunner(t, max_extra_replies=3).run(RUN, "c-1")
    assert [b.get("text") for b in t.sent[2:]] == ["More detail.", LAST_REPLY, LAST_REPLY]
    assert "still in intake after 3" in result.problems[0]


def test_a_step_that_arrives_after_the_deadline_is_a_problem():
    ticks = iter([0, 61])  # turn 1 sets its deadline at 0 and its step arrives at 61 s
    t = FakeTransport(step("intake", ["end"]), step("playback", ["confirm_playback", "end"]))
    result = ScenarioRunner(t, clock=lambda: next(ticks)).run(RUN, "c-1")
    assert "did not arrive within 60 s" in result.problems[0]


def test_the_agentcore_dataset_and_invoker_send_each_scenario_turn_in_order():
    # Spec 36: with the AgentCore client stubbed, a scenario's turns become the right request sequence.
    from bedrock_agentcore.evaluation.runner.invoker_types import AgentInvokerInput

    [scenario] = agentcore_dataset([RUN])
    assert scenario.scenario_id == "R1" and [t.input["turn"] for t in scenario.turns] == [0, 1, 2]
    t = FakeTransport(step("intake", ["end"]), step("playback", ["confirm_playback", "end"]),
                      step("consent", ["set_consent", "end"]))
    invoker = AgentCoreInvoker(ScenarioRunner(t), [RUN])
    outputs = [invoker(AgentInvokerInput(payload=turn.input, session_id="sess-1")).agent_output for turn in scenario.turns]
    assert t.sent == [{"kind": "start"}, {"kind": "message", "text": "Hello."},
                      {"kind": "action", "action": {"name": "confirm_playback", "args": {}}}]
    assert [o["steps"] for o in outputs] == [["intake"], ["playback"], ["consent"]] and not outputs[-1]["problems"]


# ------------------------------------------------------------------ the dataset

def test_the_dataset_has_every_scenario_contrast_run_and_labeled_account():
    assert len(scenario_runs()) == 9 and len(labeled_runs()) == 15
    account = labeled_runs()[0]
    assert [t.get("action", {}).get("name") for t in account.turns] == [None, "confirm_playback", "set_consent", "end"]


def test_pair_runs_match_the_contrast_pairs_from_7():
    for pair in contrast_pairs():
        a, b = PAIR_RUNS[pair["pair_id"]]
        assert {RUNS[a].producer_id, RUNS[b].producer_id} == set(pair["producers"]), pair["pair_id"]


# ------------------------------------------------------------------ distinctness and the report

def test_the_reviewer_mark_decides_a_pair_and_marks_from_another_run_are_stale(sessions):
    rows = {r["pair"]: r for r in pair_rows(sessions, "run-1", {"run_id": "run-1", "marks": {"C4": "tailored", "C1": "generic"}})}
    assert rows["C4"]["jaccard"] is not None and rows["C4"]["mark_only"]
    assert rows["C4"]["passes"] is True, "a high number never overrides a tailored mark"
    assert rows["C1"]["passes"] is False and rows["C3"]["mark_status"] == "pending"
    stale = {r["pair"]: r for r in pair_rows(sessions, "run-2", {"run_id": "run-1", "marks": {"C4": "tailored"}})}
    assert stale["C4"]["mark_status"] == "stale" and stale["C4"]["passes"] is None


def test_the_report_scores_completed_runs_and_scores_a_declined_run_only_on_its_outcome(sessions):
    report = score(list(sessions.values()), None, "run-1", marks={"run_id": None, "marks": {}}, real_services=False)
    scored = {r["run_id"] for r in report["results"]}
    assert "S4" not in scored and {"S1", "L01"} <= scored, "S4 declines"
    assert {o["run_id"] for o in report["outcomes"]} >= {"S1", "S4"}
    assert report["failures"] == []
    assert [r["evaluator"] for r in report["results"] if r["run_id"] == "L01"][0] == "tag_overlap"
    counted = {t["metric"]: t["counted"] for t in report["summary"]["targets"]}
    assert counted["Mean tone score"] is False, "an uncalibrated judge's scores are not counted"
    assert "# Eval run run-1" in markdown(report)


def test_a_judge_counts_only_after_its_calibration_met_the_threshold(tmp_path):
    path = tmp_path / "cal.json"
    judge = StubJudge()
    assert not judge_calibrated(judge, path)
    path.write_text(json.dumps({"model_id": "stub-judge", "threshold": 0.8, "tone_agreement": 0.9,
                                "support_agreement": 0.7}))
    assert not judge_calibrated(judge, path)
    path.write_text(json.dumps({"model_id": "stub-judge", "threshold": 0.8, "tone_agreement": 0.9,
                                "support_agreement": 0.85}))
    assert judge_calibrated(judge, path) and not judge_calibrated(None, path)
