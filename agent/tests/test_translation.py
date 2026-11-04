"""#22 (changed 2026-11-04): the reviewer's English summary comes from Amazon Translate, the model's is the fallback."""
from tests.conversation_harness import RETRIEVE, Run, intake, playback, summary

from fex.translate import AmazonTranslator


class FakeTranslator:
    def __init__(self, result: str = "Rainfall dropped a lot.", fail: Exception | None = None):
        self.result, self.fail, self.calls = result, fail, []

    def translate(self, text: str, source: str, target: str) -> str:
        self.calls.append((text, source, target))
        if self.fail:
            raise self.fail
        return self.result


def confirm(r: Run):
    r.to_playback()
    r.small.add(summary())  # the model's own English: "Rain fell."
    r.large.add(*RETRIEVE, r.good_answer())
    return r.action("confirm_playback")


def test_spanish_summary_english_is_the_translators_output():
    t = FakeTranslator()
    r = Run(translator=t)
    confirm(r)
    assert t.calls == [("La lluvia bajó.", "es", "en")]
    assert r.state().playback.summary_english == "Rainfall dropped a lot."


def test_a_failing_translator_falls_back_to_the_models_english_and_logs_it():
    r = Run(translator=FakeTranslator(fail=RuntimeError("throttled")))
    confirm(r)
    assert r.state().playback.summary_english == "Rain fell."
    assert any(e.kind == "step" and e.code == "translation_fallback" for e in r.state().decision_log)


def test_without_a_translator_the_models_english_is_used():  # demo mode: no AWS
    r = Run()
    confirm(r)
    assert r.state().playback.summary_english == "Rain fell."
    assert not any(e.code == "translation_fallback" for e in r.state().decision_log)


def test_an_english_conversation_calls_no_translator():
    t = FakeTranslator()
    r = Run(translator=t)
    r.small.add(intake("What has been difficult?", language="en"), intake("", ready=True, language="en"), playback())
    r.send("start")
    r.send("message", text="Rain dropped and the harvest fell.")
    r.small.add(summary())
    r.large.add(*RETRIEVE, r.good_answer())
    r.action("confirm_playback")
    assert r.state().language == "en" and t.calls == []
    assert r.state().playback.summary_english is None


class FakeTranslateClient:
    def __init__(self):
        self.calls = []

    def translate_text(self, **kwargs):
        self.calls.append(kwargs)
        return {"TranslatedText": "Rain fell.", "SourceLanguageCode": "es", "TargetLanguageCode": "en"}


def test_amazon_translator_calls_translate_text_with_the_language_codes():
    client = FakeTranslateClient()
    assert AmazonTranslator(client=client).translate("La lluvia bajó.", "es", "en") == "Rain fell."
    assert client.calls == [{"Text": "La lluvia bajó.", "SourceLanguageCode": "es", "TargetLanguageCode": "en"}]
