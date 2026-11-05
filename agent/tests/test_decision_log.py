"""Decision log entries (#26): step changes, data tool calls and PII findings, as they happen.

Spec: docs/specs/26-write-back.md ("Decision log and AI usage", `decision_log` row). Verifier and backstop
entries are covered in test_standards_tool.py; PII entries in test_pii.py.
"""
import re

from tests.conversation_harness import Run, summary

from fex.models import DECISION_REF

DATA_TOOLS = ["get_producer_record", "get_regional_context", "find_peer_examples", "find_standards"]


def logged(run: Run, code: str) -> list[list[str]]:
    return [e.refs for e in run.state().decision_log if e.code == code]


def test_each_step_change_is_logged_once_in_order():
    run = Run()
    run.to_feedback()
    assert logged(run, "step_changed") == [["intake"], ["intake", "playback"], ["playback", "respond"],
                                          ["respond", "consent"], ["consent", "feedback"]]
    assert {e.kind for e in run.state().decision_log if e.code == "step_changed"} == {"step"}


def test_a_turn_that_keeps_the_step_logs_no_step_change():
    run = Run()
    run.to_consent()
    before = logged(run, "step_changed")
    run.action("set_consent", scope="declined")  # stays in consent
    assert logged(run, "step_changed") == before


def test_closing_is_logged_as_a_step_change():
    run = Run()
    run.to_feedback()
    run.action("end")
    assert logged(run, "step_changed")[-1] == ["feedback", "closed"]


def test_each_data_tool_run_is_logged_with_the_ids_it_returned():
    run = Run()
    run.to_consent()
    calls = {refs[0]: refs[1:] for refs in logged(run, "tool_called")}
    assert sorted(calls) == sorted(DATA_TOOLS)
    regional_id = re.search(r"\[([^\[\]]+)\]\s*$", run.regional[0]["source"]).group(1)
    assert regional_id in calls["get_regional_context"]
    assert "APS 1.1" in calls["find_standards"]
    assert all(re.match(DECISION_REF, ref) for refs in calls.values() for ref in refs)


def test_a_backstopped_tool_is_logged_as_backstopped_then_called():
    run = Run()
    run.to_playback()
    run.small.add(summary())
    run.large.add(("tool", "get_regional_context", {}), ("text", "done"), run.good_answer())
    run.action("confirm_playback")
    tool_entries = [(e.code, e.refs[0]) for e in run.state().decision_log if e.kind == "tool"]
    assert tool_entries == [("tool_called", "get_regional_context"),
                            ("tool_backstopped", "get_producer_record"), ("tool_called", "get_producer_record"),
                            ("tool_backstopped", "find_peer_examples"), ("tool_called", "find_peer_examples"),
                            ("tool_backstopped", "find_standards"), ("tool_called", "find_standards")]
