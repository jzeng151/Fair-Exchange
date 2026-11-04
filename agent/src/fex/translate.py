"""Amazon Translate for reviewer-facing English (#22, changed 2026-11-04).

The conversation itself is never machine-translated: Claude speaks the producer's language. Only the English
summary reviewers read comes from Amazon Translate, so it is a translation from a dedicated service rather than a
model paraphrase. The engine keeps the model's English summary as the fallback if a call fails.
"""
from typing import Any, Protocol


class Translator(Protocol):
    def translate(self, text: str, source: str, target: str) -> str: ...


class AmazonTranslator:
    """Amazon Translate `TranslateText`. The client is created on first use, so tests and demo mode need no AWS."""

    def __init__(self, client: Any = None, region: str | None = None) -> None:
        self._client, self._region = client, region

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3
            self._client = boto3.client("translate", region_name=self._region)
        return self._client

    def translate(self, text: str, source: str, target: str) -> str:
        response = self.client.translate_text(Text=text, SourceLanguageCode=source, TargetLanguageCode=target)
        return response["TranslatedText"]
