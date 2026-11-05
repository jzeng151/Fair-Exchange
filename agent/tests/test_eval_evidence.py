"""Eval evidence capture (#34's shared contract, used by the #36 harness).

At the end of each respond step and at close, an engine with an evidence store records what the data
tools returned, the claims the producer was shown, the codes of claims dropped after the last retry and
the step the conversation is in. Without a store (the main stack), nothing is captured.
"""
from tests.conversation_harness import RETRIEVE, Run, answer, claim, of, playback, summary

from fex.conversation import ConversationEngine
from fex.eval_evidence import EvalEvidence, InMemoryEvidenceStore


def capturing(run: Run) -> InMemoryEvidenceStore:
    store = InMemoryEvidenceStore()
    run.engine.evidence_store = store
    return store


def test_an_answer_records_every_tool_result_the_shown_claims_and_the_step():
    r = Run()
    store = capturing(r)
    events = r.to_consent()
    ev = store.get(r.conversation_id)
    assert isinstance(ev, EvalEvidence) and ev.producer_id == r.producer_id and ev.final_step == "consent"
    [ans] = ev.answers
    kinds = {item["kind"] for item in ans.tool_results}
    assert {"producer_record", "regional", "peer", "standard"} <= kinds
    assert all(item["text"] and item["source"] for item in ans.tool_results), "full items, not just labels"
    shown = [(c.section, c.claim.text) for c in ans.claims]
    assert shown == [(c.section, c.claim.text) for c in of(events, "claim")]
    assert ans.dropped == [] and not ans.failed
    assert ev.item_for(ans.claims[0].claim.citation.source)["kind"] == "regional"


def test_claims_dropped_after_the_last_retry_record_their_codes():
    r = Run()
    store = capturing(r)
    r.to_playback()
    r.small.add(summary())
    bad = claim("Invented.", "Made-up source")
    r.large.add(*RETRIEVE, answer([bad], [claim("Peer.", r.peers[0]["source"])]), answer([bad], []), answer([bad], []))
    r.action("confirm_playback")
    [ans] = store.get(r.conversation_id).answers
    assert [c.claim.text for c in ans.claims] == ["Peer."]
    assert ans.dropped == ["unknown_source"]


def test_a_reopened_conversation_keeps_every_answer_in_order():
    r = Run()
    store = capturing(r)
    r.to_consent()
    r.small.add(playback("Entiendo, de nuevo."), summary())
    r.action("reopen_playback")
    r.large.add(*RETRIEVE, answer([claim("Second insight.", r.regional[0]["source"])],
                                  [claim("Second peer.", r.peers[0]["source"])]))
    r.action("confirm_playback")
    ev = store.get(r.conversation_id)
    assert [[c.claim.text for c in a.claims] for a in ev.answers] == [
        ["Rainfall fell.", "A peer built tanks."], ["Second insight.", "Second peer."]]
    assert ev.final_step == "consent"


def test_a_failed_answer_is_recorded_and_the_retry_adds_another():
    r = Run()
    store = capturing(r)
    r.to_playback()
    r.small.add(summary())
    r.large.add(("tool", "get_producer_record", {}), ("raise", RuntimeError("model down")))
    r.action("confirm_playback")
    ev = store.get(r.conversation_id)
    [failed] = ev.answers
    assert failed.failed and failed.claims == []
    assert {item["kind"] for item in failed.tool_results} == {"producer_record"}, "items returned before the failure"
    assert ev.final_step == "respond"
    r.large.add(*RETRIEVE, r.good_answer())
    r.action("retry_answer")
    ev = store.get(r.conversation_id)
    assert [a.failed for a in ev.answers] == [True, False] and ev.final_step == "consent"


def test_close_after_a_reload_keeps_the_answers_and_records_the_final_step():
    r = Run()
    store = capturing(r)
    r.to_feedback()
    before = store.get(r.conversation_id).answers
    fresh = ConversationEngine(store=r.store, small_model=r.small, large_model=r.large, retriever=r.retriever,
                               clock=r._clock, evidence_store=store)
    fresh.handle({"kind": "action", "producerId": r.producer_id, "conversationId": r.conversation_id,
                  "action": {"name": "end", "args": {}}})
    ev = store.get(r.conversation_id)
    assert ev.final_step == "closed" and ev.answers == before


def test_without_a_store_nothing_is_captured():
    r = Run()
    assert r.engine.evidence_store is None
    r.to_feedback()


def test_a_store_failure_never_breaks_the_conversation():
    class Broken(InMemoryEvidenceStore):
        def put(self, evidence):
            raise RuntimeError("bucket unavailable")

    r = Run()
    r.engine.evidence_store = Broken()
    events = r.to_consent()
    assert not of(events, "error") and of(events, "answer")
