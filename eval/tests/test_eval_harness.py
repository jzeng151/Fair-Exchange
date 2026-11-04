"""The harness's own tests (#36), hermetic: real #35 fixtures, stub transports + record
models, a stub judge. No AWS calls, no network. The live path (`runner.main`) drives the
deployed chat API and is exercised in the workshop; the pieces it uses are all covered here.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fex.models import (
    ChallengeTag,
    Claim,
    Citation,
    CompletedRecord,
    DeclinedConsent,
    DeclinedRecord,
    StoredConsent,
)
from fx_evals.evaluators import Registry, run_evaluators
from fx_evals.judge import parse_rubric
from fx_evals.runner import (
    build_dataset,
    distinctness_pairs,
    distinctness_violation,
    load_contrast_config,
    load_reference,
    load_scenarios,
    pair_answers,
    repo_root,
    run_offline,
    write_report,
)
from fx_evals.scenario_runner import StubChatTransport, drive
from fx_evals.sessions import (
    EVIDENCE_BUCKET_ENV,
    RECORDS_TABLE_ENV,
    EvalEvidence,
    ReferenceData,
    Session,
    SessionDirectory,
)

EVAL = Path(__file__).resolve().parents[1]
ROOT = repo_root()
NOW = datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)
STEP_DONE = [{"step": {"kind": "summary"}, "summary": {"text": "ok"}},
             {"step": {"kind": "done"}, "done": {}}]


def _record(session_id: str, producer_id: str, *, language: str = "en",
            tags: tuple[str, ...] = ("market and price",), evidence: str = "full",
            insights: list[tuple[str, str, str]] | None = None,
            peers: list[tuple[str, str, str]] | None = None,
            summary: str | None = None, english: str | None = None,
            scope: str = "internal", feedback: str | None = None,
            pii_flag: bool = False) -> CompletedRecord:
    text = summary or "Prices dropped across the valley this season."
    return CompletedRecord(
        status="completed",
        record_id=session_id,
        producer_id=producer_id,
        created_at=NOW,
        updated_at=NOW,
        version=1,
        consent=StoredConsent(scope=scope, recorded_at=NOW),
        feedback=feedback,
        pii_flag=pii_flag,
        language=language,
        entity_type="smallholder",
        summary_original=text,
        summary_english=None if language == "en" else (english or text),
        tags=list(tags),
        evidence=evidence,
        insights=[Claim(text=t, citation=Citation(source=s, standard_clause=c))
                  for t, s, c in (insights or ())],
        peer_examples=[Claim(text=t, citation=Citation(source=s, standard_clause=c))
                       for t, s, c in (peers or ())],
    )


def _evidence(session_id: str, tool_items: list[dict], clauses: list[str]) -> EvalEvidence:
    return EvalEvidence(
        conversation_id=session_id, final_step="done",
        tool_items=tool_items, clauses=clauses)


def _session(session_id: str, record, evidence: EvalEvidence | None = None) -> Session:
    return Session(session_id=session_id, record=record, evidence=evidence)


class JudgeStub:
    """The judge seam: anything with .score(text) -> (1..5, rationale)."""

    def __init__(self, score: int = 5):
        self.score_value = score
        self.texts: list[str] = []

    def score(self, text: str) -> tuple[int, str]:
        self.texts.append(text)
        return self.score_value, "clear options, no directives"


GOOD_CITATIONS = ("It rained less this year than the record for the valley.",
                  "producer-record:sample-01", "APS 3.2.1")
GOOD_PEER = ("A cooperative nearby ran a shared seed fund for replanting.",
             "peer-project:sample-02", "APS 4.1.0")


def _good_record(session_id: str, producer_id: str) -> CompletedRecord:
    return _record(
        session_id, producer_id,
        tags=("market and price", "climate and weather"),
        insights=[GOOD_CITATIONS],
        peers=[GOOD_PEER],
    )


def _good_evidence(session_id: str) -> EvalEvidence:
    return _evidence(
        session_id,
        tool_items=[
            {"tool": "get_producer_record", "source": "producer-record:sample-01",
             "data": {"summary": "coffee prices"}},
            {"tool": "peer_examples", "source": "peer-project:sample-02", "data": {}},
        ],
        clauses=["APS 3.2.1", "APS 4.1.0"],
    )


# --- fixtures vs reference inputs -------------------------------------------------------


def test_load_scenarios_and_reference():
    scenarios = load_scenarios(ROOT / "eval" / "scenarios")
    assert len(scenarios) >= 5
    references = load_reference(scenarios)
    ids = {s["id"] for s in scenarios}
    assert set(references) == ids
    for scenario in scenarios:
        reference = references[scenario["id"]]
        assert reference.reference_tags == scenario["expect"]["tags"], scenario["id"]
        assert reference.forbidden, f"scope-leak needles for {scenario['id']}"
        for scenario_id in ids - {scenario["id"]}:
            producer_id = next(s["producer_id"] for s in scenarios if s["id"] == scenario_id)
            assert producer_id in reference.forbidden, f"other producers' ids in {scenario['id']}"


# --- the scenario runner -----------------------------------------------------------------


def test_drive_sends_producer_identity_and_every_turn():
    scenarios = load_scenarios(ROOT / "eval" / "scenarios")
    for scenario in scenarios:
        stub = StubChatTransport(f"conv-{scenario['id']}", STEP_DONE)
        conversation_id = drive(scenario, stub)
        assert conversation_id == f"conv-{scenario['id']}"
        kinds = [call[0] for call in stub.calls]
        assert kinds[0] == "create" and kinds[-1] == "actions"
        producer_id, language = stub.calls[0][1]["producer_id"], stub.calls[0][1]["language"]
        assert producer_id == scenario["producer_id"] and language == scenario["language"]
        messages = [call[1][1] for call in stub.calls if call[0] == "message"]
        expected = [turn["text"] for turn in scenario["turns"] if turn["kind"] == "message"]
        assert messages == expected
        actions = [call[1][1]["action"] for call in stub.calls if call[0] == "actions"]
        expected = [turn["action"]["name"] for turn in scenario["turns"] if turn["kind"] == "action"]
        assert actions == expected
        for call in stub.calls[1:]:
            assert call[1][0] == conversation_id  # conversation id threaded into every call


def test_drive_unknown_turn_kind_raises():
    stub = StubChatTransport("conv-x", STEP_DONE)
    with pytest.raises(ValueError, match="unknown turn kind"):
        drive({"id": "x", "producer_id": "p", "language": "en",
               "turns": [{"kind": "teleport"}]}, stub)


def test_drive_failed_step_raises():
    stub = StubChatTransport("conv-x", [{"step": {"kind": "failed"}, "error": {"code": "boom"}}])
    with pytest.raises(AssertionError, match="reported a failed step"):
        drive({"id": "x", "producer_id": "p", "language": "en",
               "turns": [{"kind": "message", "text": "hi"}]}, stub)


# --- the six evaluators over model records ----------------------------------------------


def _run_all(session: Session, reference: ReferenceData, judge) -> dict[str, dict]:
    results = run_evaluators(session, reference, judge)
    return {r["evaluator_id"]: r for r in results}


def test_completed_record_scores_clean():
    session = _session("s-ok", _good_record("s-ok", "P1"), _good_evidence("s-ok"))
    reference = ReferenceData(scenario_id="x", reference_tags=["water", "market and price"],
                              forbidden=["P-other"])
    report = run_evaluators(session, reference, JudgeStub(5))
    by_id = {r["evaluator_id"]: r for r in report}
    assert list(by_id) == ["tag_overlap", "citation_validity", "answer_completeness",
                           "directive_language", "enablement_tone", "scope_leak"]
    assert by_id["tag_overlap"]["value"] == pytest.approx(1 / 3)  # 1 common / 3 union
    assert by_id["citation_validity"]["value"] == 1.0
    assert by_id["answer_completeness"]["value"] == 1.0
    assert by_id["directive_language"]["value"] == 1.0
    assert by_id["enablement_tone"]["value"] == 1.0
    assert by_id["scope_leak"]["value"] == 0.0  # post-flip: 0.0=clean, 1.0=leak


def test_tag_overlap_jacard_and_target():
    record = _record("s-t", "P1", tags=("water", "soil and land"))
    session = _session("s-t", record)
    reference = ReferenceData(scenario_id="x", reference_tags=["water", "climate and weather"])
    overlap = run_evaluators(session, reference, JudgeStub())[0]
    assert overlap["evaluator_id"] == "tag_overlap"
    assert overlap["value"] == pytest.approx(1 / 3)  # 1 common / 3 union
    assert overlap["breakdown"]["target"] == 0.80


def test_citation_validity_flags_unknown_source_and_clause():
    record = _record("s-c", "P1", insights=[GOOD_CITATIONS,
                                            ("Unsourced claim.", "mystery_tool", "APS 9.9.9")])
    session = _session("s-c", record, _good_evidence("s-c"))
    result = run_evaluators(session, ReferenceData(scenario_id="x"), JudgeStub())[1]
    assert result["evaluator_id"] == "citation_validity"
    assert result["value"] == pytest.approx(1 / 2)
    errors = result["breakdown"]["problems"][0]["errors"]
    assert "source_not_in_conversation:mystery_tool" in errors
    assert "clause_not_retrieved:APS 9.9.9" in errors


def test_directive_language_flags_english_and_spanish():
    base = ("Record summary is fine.", )
    for phrase, language, summary in (
        ("you should try", "en", None),
        ("usted debe decidir", "es", "Debe decidir usted mismo."),
    ):
        record = _record("s-d", "P1", language=language,
                         insights=[(f"{base[0]} {phrase}", "get_producer_record", "APS 3.2.1")],
                         summary=summary if language == "es" and phrase.startswith("usted") else None,
                         english="You must decide." if language == "es" else None)
        session = _session("s-d", record)
        result = run_evaluators(session, ReferenceData(scenario_id="x"), JudgeStub())[3]
        assert result["value"] == 0.0, phrase
        assert result["breakdown"]["matches"][0]["phrase"] in phrase


def test_scope_leak_flags_other_producer_in_record_and_evidence():
    record = _record("s-s", "P1", insights=[("Contact coop P-other for details.",
                                             "get_producer_record", "APS 3.2.1")])
    session = _session("s-s", record)
    result = run_evaluators(session, ReferenceData(scenario_id="x", forbidden=["P-other"]),
                            JudgeStub())[5]
    assert result["value"] == 1.0  # post-flip: leak scores 1.0
    assert result["breakdown"]["matches"][0]["where"] == "record"

    clean_record = _record("s-s2", "P1")
    evidence = _evidence("s-s2", tool_items=[
        {"tool": "get_regional_context", "source": "regional:sample", "data": "peer P-other data"}],
        clauses=[])
    session2 = _session("s-s2", clean_record, evidence)
    result2 = run_evaluators(session2, ReferenceData(scenario_id="x", forbidden=["P-other"]),
                             JudgeStub())[5]
    assert result2["value"] == 1.0  # post-flip: leak in evidence scores 1.0
    assert result2["breakdown"]["matches"][0]["where"] == "tool_item"


def test_declined_record_values():
    record = DeclinedRecord(
        status="declined",
        record_id="s-x", producer_id="P1", created_at=NOW, updated_at=NOW, version=1,
        consent=DeclinedConsent(scope="declined", recorded_at=NOW))
    session = _session("s-x", record)
    results = run_evaluators(session, ReferenceData(scenario_id="x", reference_tags=["water"]),
                             JudgeStub())
    by_id = {r["evaluator_id"]: r for r in results}
    assert by_id["tag_overlap"]["value"] == 0.0
    assert by_id["citation_validity"]["value"] == 1.0  # nothing shown, nothing invalid
    assert by_id["answer_completeness"]["value"] == 0.0
    assert by_id["directive_language"]["value"] == 1.0
    assert by_id["enablement_tone"]["value"] == 0.0
    assert by_id["scope_leak"]["value"] == 0.0  # declined: nothing shown, clean


def test_judge_scores_normalized_and_judge_seam_runs_stub():
    judge = JudgeStub(4)
    session = _session("s-j", _good_record("s-j", "P1"))
    result = run_evaluators(session, ReferenceData(scenario_id="x"), judge)[4]
    assert result["value"] == pytest.approx(0.8)
    assert result["breakdown"]["score"] == 4
    assert judge.texts, "the judge received the shown answer text"


def test_parse_rubric_reads_score_line():
    score, rationale = parse_rubric("Rationale: solid. Score: 4. Notes.")
    assert score == 4 and "solid" in rationale


# --- the offline run: runner_fn seam, distinctness, report -------------------------------


def test_run_offline_registry_seam_and_report(tmp_path):
    scenarios = [{"id": "alpha", "producer_id": "P1", "language": "en",
                  "turns": [{"kind": "message", "text": "bad harvest"},
                            {"kind": "action", "action": {"name": "confirm_playback",
                                                          "args": {}}}]}]
    references = load_reference(load_scenarios(ROOT / "eval" / "scenarios"))
    stores = SessionDirectory(
        records={"conv-alpha": _good_record("conv-alpha", "P1")},
        evidence={"conv-alpha": _good_evidence("conv-alpha")})
    seen: list[tuple[str, str]] = []

    def seam(session, reference, judge):
        seen.append((session.session_id, reference.scenario_id))
        judge.score("probe")
        return [{"evaluator_id": "custom", "session_id": session.session_id,
                 "value": 1.0, "breakdown": {}}]

    report = run_offline(
        scenarios=scenarios,
        references=load_reference(scenarios),
        transport_factory=lambda: StubChatTransport("conv-alpha", STEP_DONE),
        stores=stores,
        evaluator_registry=seam,
        judge=JudgeStub(),
        contrast_config={"pairs": [], "reviewer_marks": {}},
    )
    assert seen == [("conv-alpha", "alpha")]
    assert report["results"] == [{"evaluator_id": "custom", "session_id": "conv-alpha",
                                  "value": 1.0, "breakdown": {}}]
    assert report["distinctness"] == {"pairs_checked": 0, "violations": [],
                                      "pair_answers": []}
    json_path, md_path = write_report(report, tmp_path)
    assert json.loads(json_path.read_text())["results"] == report["results"]
    assert md_path.read_text().startswith("# Eval run")


def test_run_offline_full_with_real_fixtures(tmp_path):
    scenarios = load_scenarios(ROOT / "eval" / "scenarios")
    references = load_reference(scenarios)
    stores = SessionDirectory()
    for scenario in scenarios:
        session_id = f"conv-{scenario['id']}"
        expect = scenario.get("expect", {}).get("record", {})
        if expect.get("status") == "declined":
            stores.add_record(session_id, DeclinedRecord(
                status="declined", record_id=session_id,
                producer_id=scenario["producer_id"], created_at=NOW, updated_at=NOW,
                version=1, consent=DeclinedConsent(scope="declined", recorded_at=NOW)))
        else:
            stores.add_record(session_id, _record(
                session_id, scenario["producer_id"],
                tags=tuple(references[scenario["id"]].reference_tags) or ("market and price",),
                scope=expect.get("consent_scope", "internal"),
                feedback=expect.get("feedback"),
                pii_flag=expect.get("pii_flag", False)))
        stores.add_evidence(session_id, _good_evidence(session_id))
    transports = iter([StubChatTransport(f"conv-{s['id']}", STEP_DONE) for s in scenarios])
    report = run_offline(
        scenarios=scenarios, references=references,
        transport_factory=lambda: next(transports),
        stores=stores, evaluator_registry=run_evaluators, judge=JudgeStub(4))
    assert len(report["results"]) == 6 * len(scenarios)
    assert report["distinctness"]["violations"] == []
    blocks = report["distinctness"]["pair_answers"]
    assert blocks, "the committed contrast pair produced a side-by-side block"
    assert blocks[0]["reviewer_mark"] is None
    paths = write_report(report, tmp_path)
    assert len(paths) == 2


def test_distinctness_violation_shared_cited_data():
    one = _session("s1", _record(
        "s1", "P1", insights=[GOOD_CITATIONS], peers=[GOOD_PEER]))
    twin = _session("s2", _record(
        "s2", "P1", insights=[GOOD_CITATIONS], peers=[GOOD_PEER]))
    other = _session("s3", _record(
        "s3", "P2", insights=[("New region story entirely.",
                               "get_regional_context", "APS 5.0.0")]))
    assert distinctness_violation(one, twin) is True
    assert distinctness_violation(one, other) is False
    assert distinctness_violation(one, _session("s4", _record(
        "s4", "P1"))) is not True  # one empty side: no union, no violation


def test_distinctness_drops_own_record_sources_and_keeps_clause_ids():
    """Finding #10: identical clauses cited from each producer's own record are one
    generic answer, not two distinct ones — the source string must not mask that."""
    own = _session("s3", _record(
        "s3", "P1", insights=[GOOD_CITATIONS]))  # producer-record:sample-01
    mirror = _session("s4", _record(
        "s4", "P2", insights=[("It rained less this year than the record "
                               "for the valley.",
                               "producer-record:other-producer",
                               "APS 3.2.1")]))
    assert distinctness_violation(own, mirror) is True
    # cited peer and regional sources keep their IDs: identical peer citation violates
    one = _session("s1", _record("s1", "P1", peers=[GOOD_PEER]))
    twin = _session("s2", _record("s2", "P2", peers=[GOOD_PEER]))
    assert distinctness_violation(one, twin) is True


def test_distinctness_pairs_are_the_declared_cross_producer_ones():
    sessions = {
        "sA": _session("sA", _record("sA", "P1", peers=[GOOD_PEER])),
        "sB": _session("sB", _record("sB", "P2", peers=[GOOD_PEER])),
        "sC": _session("sC", _record("sC", "P3", peers=[GOOD_PEER])),
    }
    rows = distinctness_pairs(sessions, pairs=[
        {"a": "sA", "b": "sB", "basis": "same tag"},
        {"a": "sA", "b": "sZ"},
    ])
    assert rows[0] == {"a": "sA", "b": "sB", "basis": "same tag",
                       "missing": [], "violation": True}
    assert rows[1]["missing"] == ["sZ"] and rows[1]["violation"] is None
    # same-producer sessions are never auto-paired: only what the config declares

    answers = pair_answers(sessions, rows, {"sA|sB": "tailored"})
    assert answers[0]["reviewer_mark"] == "tailored"
    assert answers[0]["sides"][0]["scenario_id"] == "sA"
    assert answers[0]["sides"][0]["peer_examples"] == [GOOD_PEER[0]]
    assert [s["scenario_id"] for s in answers[1]["sides"]] == ["sA"]


def test_distinctness_config_declares_real_contrast_pairs():
    """The committed config must name scenario fixtures that exist (#7 pair list
    lands later as a config edit, not a code change)."""
    config = load_contrast_config()
    scenario_ids = {p.stem for p in (ROOT / "eval" / "scenarios").glob("*.json")}
    for pair in config["pairs"]:
        assert pair["a"] in scenario_ids and pair["b"] in scenario_ids
        assert pair["a"] != pair["b"]


def test_run_offline_reports_pair_side_by_sides(tmp_path):
    scenarios = [{"id": "alpha", "producer_id": "P1", "language": "en",
                  "turns": [{"kind": "message", "text": "bad harvest"}]},
                 {"id": "beta", "producer_id": "P2", "language": "en",
                  "turns": [{"kind": "message", "text": "bad harvest"}]}]
    stores = SessionDirectory(
        records={"conv-alpha": _good_record("conv-alpha", "P1"),
                 "conv-beta": _good_record("conv-beta", "P2")},
        evidence={})
    transports = iter([StubChatTransport("conv-alpha", STEP_DONE),
                       StubChatTransport("conv-beta", STEP_DONE)])
    report = run_offline(
        scenarios=scenarios, references=load_reference(scenarios),
        transport_factory=lambda: next(transports), stores=stores,
        evaluator_registry=lambda *a, **k: [], judge=JudgeStub(),
        contrast_config={"pairs": [{"a": "alpha", "b": "beta",
                                    "basis": "same tag"}],
                         "reviewer_marks": {"alpha|beta": "tailored"}})
    assert report["distinctness"]["pairs_checked"] == 1
    assert report["distinctness"]["violations"] == ["alpha vs beta"]
    block = report["distinctness"]["pair_answers"][0]
    assert block["reviewer_mark"] == "tailored"
    assert [s["scenario_id"] for s in block["sides"]] == ["alpha", "beta"]
    json_path, md_path = write_report(report, tmp_path)
    md = md_path.read_text()
    assert "- pair alpha vs beta [tailored]" in md
    assert "  - alpha:" in md


# --- the AgentCore dataset shape ---------------------------------------------------------


def test_build_dataset_shape():
    scenarios = load_scenarios(ROOT / "eval" / "scenarios")
    references = load_reference(scenarios)
    entries = build_dataset(scenarios, references)
    assert len(entries) == len(scenarios)
    for entry in entries:
        assert entry["scenario_id"] in references
        assert entry["assertions"] == sorted(references[entry["scenario_id"]].reference_tags)
        assert entry["metadata"]["producer_id"]


def test_env_names():
    assert RECORDS_TABLE_ENV == "EVAL_RECORDS_TABLE"
    assert EVIDENCE_BUCKET_ENV == "EVAL_EVIDENCE_BUCKET"

def test_summarize_report():
    record = _good_record("s-sum", "P1")
    reference = ReferenceData(scenario_id="x", reference_tags=["market and price"])
    report = run_offline(
        scenarios=[{"id": "s-sum", "producer_id": "P1", "turns": []}],
        references={"s-sum": reference},
        transport_factory=lambda: StubChatTransport("conv-s-sum", STEP_DONE),
        stores=SessionDirectory(
            records={"conv-s-sum": record},
            evidence={"conv-s-sum": _good_evidence("conv-s-sum")}),
        evaluator_registry=None,
        judge=JudgeStub(5),
        contrast_config={"pairs": [], "reviewer_marks": {}})
    summary = report["summary"]
    assert summary["mean_tag_overlap"] == pytest.approx(0.5)  # 1 common / 2 union
    assert summary["citation_validity"] == 1.0
    assert summary["answer_completeness"] == 1.0
    assert summary["directive_language_violations"] == 0
    assert summary["mean_tone_score"] == pytest.approx(1.0)  # judge 5/5, normalized
    assert summary["distinctness_pass_rate"] is None  # single session, no pairs
    assert summary["scope_leak_count"] == 0
    assert report["failures"] == []


def test_missing_record_is_reported_not_scored():
    class NoRecord:
        def get_record(self, session_id):  # noqa: ARG002 - seam signature
            raise LookupError(session_id)

        def get_evidence(self, session_id):  # noqa: ARG002
            raise LookupError(session_id)

    reference = ReferenceData(scenario_id="x", reference_tags=["water"])
    report = run_offline(
        scenarios=[{"id": "s-miss", "producer_id": "P1",
                    "turns": [{"id": "t1", "kind": "start", "text": "", "action": None},
                              {"id": "t2", "kind": "message", "text": "hi", "action": None}]},
                   ],
        references={"s-miss": reference},
        transport_factory=lambda: StubChatTransport("conv-s-miss", STEP_DONE),
        stores=NoRecord(),
        evaluator_registry=None,
        judge=JudgeStub(4))
    assert report["results"] == []  # never scored as zero overlap
    assert report["failures"] == [{"session_id": "conv-s-miss", "error": "no saved record"}]
    assert report["summary"]["mean_tag_overlap"] is None  # excluded from the tag mean


def test_outcome_checks_completed_matches():
    from fx_evals.runner import outcome_checks

    record = _good_record("s-out", "P1")  # scope internal, feedback None, pii False
    scenario = {"id": "s-out", "producer_id": "P1",
                "expect": {"record": {"status": "completed", "consent_scope": "internal",
                                      "feedback": "yes", "pii_flag": False}}}
    checks = outcome_checks(scenario, record)
    by_field = {c["field"]: c for c in checks}
    assert by_field["status"]["pass"] is True
    assert by_field["consent_scope"]["pass"] is True
    assert by_field["feedback"]["pass"] is False  # record has None, expected "yes"
    assert by_field["pii_flag"]["pass"] is True


def test_outcome_checks_declined():
    from fx_evals.runner import outcome_checks

    record = DeclinedRecord(
        status="declined", record_id="s-dec", producer_id="P1", created_at=NOW,
        updated_at=NOW, version=1,
        consent=DeclinedConsent(scope="declined", recorded_at=NOW))
    scenario = {"id": "s-dec", "producer_id": "P1",
                "expect": {"record": {"status": "declined", "consent_scope": "declined"}}}
    checks = outcome_checks(scenario, record)
    assert all(c["pass"] for c in checks)
    assert outcome_checks({"id": "s-none", "expect": {}}, None) == []
