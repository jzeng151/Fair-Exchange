"""Directive language FEX must never use (issue #17). Spec: docs/specs/17-standards-grounding.md.

One shared list, used by the citation verifier (a claim with a directive phrase fails) and by the
eval tone check. FEX informs; the producer and their committee decide.
"""
import re
import unicodedata

DIRECTIVE_PHRASES: dict[str, tuple[str, ...]] = {
    "en": (
        "you should", "you must", "you need to", "you have to", "you ought to",
        "we recommend", "i recommend", "we suggest", "i suggest", "we advise", "i advise",
        "the best option", "the best choice", "the right choice", "make sure you",
    ),
    "es": (
        "usted debe", "usted debería", "ustedes deben", "ustedes deberían", "debe usted", "deberías",
        "le recomendamos", "les recomendamos", "le recomiendo", "les recomiendo",
        "le sugerimos", "les sugerimos", "la mejor opción", "la mejor alternativa", "asegúrese de",
    ),
}
# Kept to second-person advice and recommendations. Third-person phrases ("los precios deberían subir",
# "tiene que") describe facts or peers as often as they direct, so the eval tone check judges those.


def _fold(text: str) -> str:
    """Lowercase, drop accents and normalize apostrophes and spacing."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("\u2019", "'"))
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


_PATTERNS = [(phrase, re.compile(rf"(?<!\w){re.escape(_fold(phrase))}(?!\w)"))
             for phrases in DIRECTIVE_PHRASES.values() for phrase in phrases]


def find_directive(text: str) -> str | None:
    """The first directive phrase in `text` (case- and accent-insensitive, whole words), or None."""
    folded = _fold(text or "")
    return next((phrase for phrase, pattern in _PATTERNS if pattern.search(folded)), None)
