"""Lightweight guardrails for the PoC chat (SDD.md: "keep within boundaries").

Mirrors the project's real guardrail intent (docs/requirements): flag, don't block the producer's
voice; refuse clearly out-of-scope asks; and keep every answer in enablement tone, never commanding.
The real system uses Amazon Bedrock Guardrails; this is a stand-in for the mock path.
"""
from __future__ import annotations

import re

# In scope: the producer's own challenges, regional data, peer examples, Fair Trade and certification.
# Out of scope for a producer-support assistant: these get a gentle redirect, not an answer.
_OUT_OF_SCOPE = [
    (re.compile(r"\b(stock tip|invest in|buy bitcoin|crypto|lottery)\b", re.I), "financial-advice"),
    (re.compile(r"\b(medical|diagnos|prescri|symptom)\b", re.I), "medical-advice"),
    (re.compile(r"\b(hack|exploit|malware|bypass)\b", re.I), "security"),
    (re.compile(r"\b(another producer|someone else'?s|other farmer'?s)\s+(data|record|site)\b", re.I),
     "cross-producer-scope"),
]

# Phrasing that would make the assistant sound commanding. We rewrite toward suggestion.
_COMMANDING = [
    (re.compile(r"\byou should\b", re.I), "you might consider"),
    (re.compile(r"\byou must\b", re.I), "it could help to"),
    (re.compile(r"\byou need to\b", re.I), "one option is to"),
    (re.compile(r"\bwe recommend\b", re.I), "some producers have found it useful to"),
    (re.compile(r"\bthe best option is\b", re.I), "one option that has worked for others is"),
    (re.compile(r"\bdo this\b", re.I), "this is one path"),
]

# PII is flagged, never redacted (a non-negotiable constraint in the vision doc).
_PII = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "email"),
    (re.compile(r"(?<!\d)(?:\+?\d[\s.-]?){7,}\d(?!\d)"), "phone"),
]


def scope_verdict(text: str) -> tuple[bool, str | None]:
    """(in_scope, reason). Out-of-scope input gets a friendly redirect rather than an answer."""
    for pattern, reason in _OUT_OF_SCOPE:
        if pattern.search(text):
            return False, reason
    return True, None


def pii_flags(text: str) -> list[str]:
    """Kinds of PII detected (flag for review, never redacted)."""
    return [kind for pattern, kind in _PII if pattern.search(text)]


def to_suggestion_tone(text: str) -> str:
    """Soften any commanding phrasing so the output suggests rather than directs."""
    for pattern, replacement in _COMMANDING:
        text = pattern.sub(replacement, text)
    return text
