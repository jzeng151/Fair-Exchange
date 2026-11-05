"""One evaluated conversation, and how an AgentCore evaluator finds which one it is scoring (#36)."""
from dataclasses import dataclass, field

from fex.eval_evidence import EvalEvidence, ShownClaim
from fex.models import CompletedRecord, DeclinedRecord

from fx_evals.runs import Run


@dataclass
class Session:
    run: Run
    conversation_id: str
    record: CompletedRecord | DeclinedRecord | None
    evidence: EvalEvidence | None
    answer_evidence: str | None = None  # `full`/`limited` from the last answer shown, declined runs included
    problems: list[str] = field(default_factory=list)

    @property
    def completed(self) -> CompletedRecord | None:
        return self.record if isinstance(self.record, CompletedRecord) else None

    def shown_claims(self) -> list[ShownClaim]:
        """Every claim the producer saw, earlier answers included. The eval evidence has them in emitted
        order; without it, the record's current and earlier answers (stored == shown, #74)."""
        if self.evidence is not None:
            return [c for answer in self.evidence.answers for c in answer.claims]
        record = self.completed
        if record is None:
            return []
        earlier = [ShownClaim(section=section, claim=c) for a in record.earlier_answers
                   for section, claims in (("insights", a.insights), ("peer_examples", a.peer_examples)) for c in claims]
        return earlier + [ShownClaim(section="insights", claim=c) for c in record.insights] + \
            [ShownClaim(section="peer_examples", claim=c) for c in record.peer_examples]


def session_id_from_payload(event: dict) -> str:
    """The session (conversation) ID in a code-based evaluator's Lambda event.

    The spike on 2026-11-05 (spec 36) found no top-level session ID. It is in the reference inputs'
    `context.spanContext.sessionId` when reference inputs are sent, and on every span as
    `attributes["session.id"]`. The spans must all carry one ID; zero or several is an error.
    """
    for ref in event.get("evaluationReferenceInputs") or []:
        if sid := ((ref.get("context") or {}).get("spanContext") or {}).get("sessionId"):
            return sid
    spans = (event.get("evaluationInput") or {}).get("sessionSpans") or []
    ids = {(s.get("attributes") or {}).get("session.id") for s in spans} - {None}
    if len(ids) != 1:
        raise ValueError(f"expected one session ID in the evaluator payload, found {len(ids)}")
    return ids.pop()
