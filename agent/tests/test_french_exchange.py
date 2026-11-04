"""Issue #24: French exchange and French PII through the Guardrail. Spec: docs/specs/24-french-exchange.md.

Seam 1 (agent entrypoint) with scripted French model output and a stubbed Guardrail scanner. French
reuses the Spanish language rules (#22); its one difference is PII: Comprehend has no French, so a
French conversation's PII goes through the FEX Guardrail (#12) instead.
"""
import boto3
import pytest
from moto import mock_aws
from tests.conversation_harness import RETRIEVE, Run, intake, of, playback, summary

from fex.conversation.state import Profile
from fex.guardrail import GuardrailPiiScanner
from fex.pii import PiiText, language_aware_scanner, scan_texts
from fex.records import DynamoRecordStore
from datetime import datetime, timezone

NOW = datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)
# A French producer text that names a person.
FR_NAME_TEXT = "Je m'appelle Kouamé Konan et la récolte de cacao a beaucoup baissé cette année."


def fr_profile(pid):
    return Profile(producer_id=pid, country="Côte d'Ivoire", region="Sud-Comoé", crop="Cocoa",
                   entity_type="smallholder", language="fr")


def fr_playback():
    return ("out", "PlaybackDraft", {"text": "Je comprends : la récolte de cacao a baissé.",
                                     "challenge": "Peu de pluie", "timing": "Deux saisons", "severity": "Élevée",
                                     "tried": "Rien encore", "entity_type": None, "location_disputed": False})


def fr_summary():
    return ("out", "RecordSummary", {"summary_original": "La récolte de cacao a baissé.",
                                     "summary_english": "The cocoa harvest fell.",
                                     "tags": ["climate and weather"]})


def langs(events) -> set[str]:
    return {e.language for e in of(events, "step") + of(events, "actions")}


# ---------------------------------------------------------------- language rules (same as #22)

def test_opening_uses_french_from_the_profile():
    r = Run(profiles=fr_profile)
    r.small.add(intake("Qu'est-ce qui a été difficile cette année ?", language="en"))  # model guess must not win
    events = r.send("start")
    assert r.state().language == "fr" and langs(events) == {"fr"}
    assert "fr" in r.small.prompts[-1]  # the model is told to open in French


def test_language_is_stored_as_fr():
    r = Run(profiles=fr_profile)
    r.small.add(intake("Qu'est-ce qui a été difficile ?", language="fr"), intake("", ready=True, language="fr"),
                fr_playback())
    r.send("start")
    r.send("message", text=FR_NAME_TEXT)
    assert r.state().language == "fr"


def test_fixed_answer_text_is_in_french():
    r = Run(profiles=fr_profile)
    r.small.add(intake("Qu'est-ce qui a été difficile ?", language="fr"), intake("", ready=True, language="fr"),
                fr_playback())
    r.send("start")
    r.send("message", text=FR_NAME_TEXT)
    r.small.add(fr_summary())
    r.large.add(*RETRIEVE, r.good_answer())
    events = r.action("confirm_playback")
    text = "".join(e.text for e in of(events, "text"))
    assert "Voici ce que j'ai trouvé" in text
    assert "Vous et votre comité connaissez le mieux votre situation" in text


# ---------------------------------------------------------------- French PII through the Guardrail

class StubGuardrailBedrock:
    """A bedrock-runtime stand-in: apply_guardrail returns a stubbed assessment, or raises."""

    def __init__(self, pii=(), raises=False):
        self.pii = list(pii)
        self.raises = raises
        self.calls = []

    def apply_guardrail(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise RuntimeError("guardrail down")
        entities = [{"type": t, "match": m, "action": "NONE", "detected": True} for t, m in self.pii]
        return {"assessments": [{"sensitiveInformationPolicy": {"piiEntities": entities}}]}


def guardrail_scanner(pii=(), raises=False) -> GuardrailPiiScanner:
    return GuardrailPiiScanner(client=StubGuardrailBedrock(pii, raises), guardrail_id="gr-1", version="1")


def fr_text(text: str) -> PiiText:
    return PiiText(text=text, message_at=NOW, kind="message")


def test_guardrail_scanner_returns_comprehend_shaped_entities():
    scanner = guardrail_scanner([("NAME", "Kouamé Konan")])
    out = scanner(FR_NAME_TEXT, "fr")
    assert out == [{"Type": "NAME", "Score": 1.0,
                    "BeginOffset": FR_NAME_TEXT.index("Kouamé Konan"),
                    "EndOffset": FR_NAME_TEXT.index("Kouamé Konan") + len("Kouamé Konan")}]
    assert scanner._client.calls[0]["source"] == "INPUT"  # input source, not output


def test_a_name_in_french_fills_the_pii_fields_with_match_and_context():
    scanner = guardrail_scanner([("NAME", "Kouamé Konan")])
    result = scan_texts([fr_text(FR_NAME_TEXT)], "fr", scanner)
    assert result.flag is True and result.check == "done"
    assert result.entity_types == ["NAME"]
    match = result.matches[0]
    assert match.entity_type == "NAME" and match.text == "Kouamé Konan"
    assert "cacao" in match.context  # context words around the match


def test_every_detected_entity_counts_without_a_threshold():
    # The Guardrail carries no score; both detections count (the 0.8 threshold is Comprehend-only).
    text = "Kouamé Konan, 07-11-22-33, kouame@coop.ci"
    scanner = guardrail_scanner([("NAME", "Kouamé Konan"), ("PHONE", "07-11-22-33"), ("EMAIL", "kouame@coop.ci")])
    result = scan_texts([fr_text(text)], "fr", scanner)
    assert result.entity_types == ["NAME", "PHONE", "EMAIL"]


def test_a_guardrail_error_marks_the_scan_failed():
    scanner = guardrail_scanner(raises=True)
    texts = [fr_text(FR_NAME_TEXT)]
    result = scan_texts(texts, "fr", scanner)
    assert result.flag is True and result.check == "failed"
    assert texts[0].status == "failed" and result.matches == []


def test_language_aware_scanner_routes_fr_to_guardrail_and_es_to_comprehend():
    comprehend_calls, guardrail_calls = [], []

    def comprehend(text, language):
        comprehend_calls.append(language)
        return []

    def guardrail(text, language):
        guardrail_calls.append(language)
        return []

    scan = language_aware_scanner(comprehend, guardrail)
    scan("texto", "es")
    scan("texte", "fr")
    assert comprehend_calls == ["es"] and guardrail_calls == ["fr"]


# ---------------------------------------------------------------- the French record (save seam)

@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        yield ddb.create_table(TableName="records", KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
                               AttributeDefinitions=[{"AttributeName": "record_id", "AttributeType": "S"}],
                               BillingMode="PAY_PER_REQUEST")


def test_the_french_record_has_both_summaries_and_is_pii_flagged(table):
    scanner = guardrail_scanner([("NAME", "Kouamé Konan")])
    r = Run(profiles=fr_profile, records=DynamoRecordStore(table), pii_scanner=scanner)
    r.small.add(intake("Qu'est-ce qui a été difficile ?", language="fr"), intake("", ready=True, language="fr"),
                fr_playback())
    r.send("start")
    r.send("message", text=FR_NAME_TEXT)
    r.small.add(fr_summary())
    r.large.add(*RETRIEVE, r.good_answer())
    r.action("confirm_playback")
    r.action("set_consent", scope="internal")

    item = table.scan()["Items"][0]
    assert item["language"] == "fr"
    assert item["summary_original"] == "La récolte de cacao a baissé."
    assert item["summary_english"] == "The cocoa harvest fell."
    assert item["pii_flag"] is True
    assert item["pii_entity_types"] == ["NAME"]
    assert item["pii_check"] == "done"
    assert "Kouamé Konan" in item["pii_matches"][0]["text"]
