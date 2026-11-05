"""Standards grounding (#17), seam 1: through the tool and through the agent entrypoint, with a fake
Knowledge Base retriever behind the same ClauseRetriever interface. Spec: docs/specs/17-standards-grounding.md.
"""
import pytest
from fx_data.records import ProducerRecords
from tests.conversation_harness import (
    RETRIEVE, FakeRetriever, Run, answer, claim, intake, of, playback, summary,
)
from tests.tool_harness import call_tool

from fex.tools.standards import BedrockKbRetriever, find_standards, standards_query
from fex.verifier import SessionEvidence

RECORDS = ProducerRecords.load()._records


def respond_state(**extra) -> dict:
    return {"producer_id": "P-1", "step": "respond", "tags": ["water"], "summary_original": "Poca lluvia.",
            "summary_english": "Little rain.", "clause_retriever": FakeRetriever(), **extra}


# ------------------------------------------------------------------ the tool

def test_returns_the_retrieved_clauses_as_standard_items():
    status, items = call_tool(find_standards, {}, respond_state())
    assert status == "success"
    assert [i["source"] for i in items] == ["APS 1.1", "APS 3.6.1"]
    for i in items:
        assert i["kind"] == "standard" and i["text"] and i["period"] is None and i["strength"] == "exact"
        assert i["data"]["clause_id"] == i["source"]


def test_standards_items_reach_the_session_evidence_and_clause_set():
    evidence = SessionEvidence()
    call_tool(find_standards, {}, respond_state(evidence=evidence))
    assert evidence.clauses == {"APS 1.1", "APS 3.6.1"}
    assert evidence.kind_of("APS 1.1") == "standard"


def test_the_query_uses_the_english_summary_and_the_tags():
    retriever = FakeRetriever()
    call_tool(find_standards, {}, respond_state(clause_retriever=retriever, tags=["water", "climate and weather"]))
    assert retriever.queries == ["Little rain. Challenges: water, climate and weather"]


def test_english_conversations_query_with_the_original_summary():
    assert standards_query({"summary_original": "Little rain.", "summary_english": None, "tags": ["water"]}) == \
        "Little rain. Challenges: water"


def test_at_most_five_distinct_clauses():
    retriever = FakeRetriever(["APS 1.1", "APS 1.1", "APS 3.6.1", "APS 2.1.1", "APS 1.2", "FPS 1.1", "APS 1.3"])
    _, items = call_tool(find_standards, {}, respond_state(clause_retriever=retriever))
    assert len(items) <= 5 and len({i["source"] for i in items}) == len(items)


@pytest.mark.parametrize("step", ["intake", "playback", "consent", "feedback", "closed", None])
def test_refuses_outside_respond(step):
    retriever = FakeRetriever()
    status, result = call_tool(find_standards, {}, respond_state(step=step, clause_retriever=retriever))
    assert status == "success" and result["refused"] is True
    assert retriever.queries == []  # nothing is retrieved before the playback is confirmed


def test_a_query_supplied_by_the_model_is_ignored():
    retriever = FakeRetriever()
    call_tool(find_standards, {"query": "forced labor"}, respond_state(clause_retriever=retriever))
    assert retriever.queries == ["Little rain. Challenges: water"]


def test_no_retriever_configured_is_a_tool_error():
    status, text = call_tool(find_standards, {}, respond_state(clause_retriever=None))
    assert status == "error" and "FEX_STANDARDS_KB_ID" in text


def test_bedrock_retriever_reads_clause_ids_from_document_metadata():
    class Client:
        def retrieve(self, **kwargs):
            self.kwargs = kwargs
            return {"retrievalResults": [
                {"content": {"text": "Clause text"}, "score": 0.8,
                 "metadata": {"clause_id": "APS 3.6.1", "standard": "APS", "x-amz-bedrock-kb-source-uri": "s3://b/k"}},
                {"content": {"text": "No clause metadata"}, "metadata": {}},
            ]}
    client = Client()
    clauses = BedrockKbRetriever("KB123", client=client).retrieve("Little rain.", 5)
    assert [(c.clause_id, c.standard, c.text) for c in clauses] == [("APS 3.6.1", "APS", "Clause text")]
    assert client.kwargs["knowledgeBaseId"] == "KB123"
    assert client.kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["numberOfResults"] == 5


# ------------------------------------------------------------------ through the agent entrypoint

def confirmed(run: Run) -> None:
    run.small.add(intake("¿Qué ha sido difícil?"), intake("", ready=True), playback())
    run.send("start")
    run.send("message", text="La lluvia bajó mucho y la cosecha cayó.")
    run.small.add(summary())


def test_a_spanish_conversation_queries_the_knowledge_base_in_english():
    r = Run()
    confirmed(r)
    r.large.add(*RETRIEVE, r.good_answer())
    r.action("confirm_playback")
    assert r.state().language == "es"
    assert r.retriever.queries == ["Rain fell. Challenges: water, climate and weather"]


def test_standards_items_reach_the_conversations_session_evidence():
    r = Run()
    r.to_consent()
    state = r.state()
    assert set(state.evidence_clauses) == {"APS 1.1", "APS 3.6.1"}
    assert state.evidence_sources["APS 1.1"] == "standard"
    assert state.evidence_sources[r.regional[0]["source"]] == "regional"
    assert state.evidence_sources[r.peers[0]["source"]] == "peer"


def test_a_tool_the_model_skipped_is_called_by_code_before_claims_are_written():
    r = Run()
    confirmed(r)
    # the model calls only the regional tool, then stops; the answer cites a peer and a retrieved clause
    r.large.add(("tool", "get_regional_context", {}), ("text", "done"), r.good_answer())
    events = r.action("confirm_playback")
    state = r.state()
    backstopped = [e.refs for e in state.decision_log if e.code == "tool_backstopped"]
    assert backstopped == [["get_producer_record"], ["find_peer_examples"], ["find_standards"]]
    assert all(e.kind == "tool" for e in state.decision_log if e.code == "tool_backstopped")
    assert r.retriever.queries  # the standards lookup ran
    # the claim-writing call saw the backstopped items
    assert r.peers[0]["source"] in r.large.prompts[-1] and "APS 3.6.1" in r.large.prompts[-1]
    assert of(events, "answer")[0].evidence == "full"


def test_every_distinct_fact_reaches_the_claim_writer_even_when_facts_share_a_source():
    # A producer whose survey facts all share one source label, as the sample data does
    pid = next(p for p, rec in RECORDS.items() if len(rec["survey"]["facts"]) > 1)
    r = Run(producer_id=pid)
    confirmed(r)
    r.large.add(*RETRIEVE, ("raise", RuntimeError("stop after the prompt is built")))
    r.action("confirm_playback")
    writer_prompt = r.large.prompts[-1]
    survey = RECORDS[pid]["survey"]["facts"]
    assert len({f["source"] for f in survey}) < len(survey)  # the case the old source-keyed dedupe lost
    for fact in survey:
        assert fact["text"] in writer_prompt
    for fact in r.regional:
        assert fact["text"] in writer_prompt


def test_a_tool_called_twice_is_only_given_to_the_claim_writer_once():
    r = Run()
    confirmed(r)
    regional = ("tool", "get_regional_context", {})
    r.large.add(regional, regional, *RETRIEVE, ("raise", RuntimeError("stop after the prompt is built")))
    r.action("confirm_playback")
    assert r.large.prompts[-1].count(r.regional[0]["text"]) == 1


def test_no_backstop_when_the_model_called_every_tool():
    r = Run()
    r.to_consent()
    assert not [e for e in r.state().decision_log if e.code == "tool_backstopped"]


def test_a_dropped_claim_logs_only_its_reason_codes():
    r = Run()
    confirmed(r)
    unretrieved = claim("Rainfall fell.", r.regional[0]["source"], clause="APS 2.1.1")
    directive = claim("You should build tanks.", r.peers[0]["source"])
    r.large.add(*RETRIEVE, answer([unretrieved], [directive]), answer([unretrieved], [directive]),
                answer([unretrieved], [directive]))
    events = r.action("confirm_playback")
    assert of(events, "claim") == []
    logged = [(e.kind, e.code) for e in r.state().decision_log if e.kind == "verifier"]
    assert sorted(logged) == [("verifier", "clause_not_retrieved"), ("verifier", "directive_language")]
    refs = [ref for e in r.state().decision_log for ref in e.refs]
    assert "APS 2.1.1" in refs and not any("Rainfall" in ref or "tanks" in ref for ref in refs)


def test_rejected_citations_cannot_copy_model_text_into_decision_references():
    r = Run()
    confirmed(r)
    private = claim("Unverified claim", "Invented [Private Person 555-0100]", clause="APS Private")
    r.large.add(*RETRIEVE, answer([private], []), answer([private], []), answer([private], []))
    r.action("confirm_playback")
    assert any(e.kind == "verifier" for e in r.state().decision_log)
    assert "Private" not in str([e.refs for e in r.state().decision_log])
