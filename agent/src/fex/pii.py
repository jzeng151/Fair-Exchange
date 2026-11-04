"""PII flagging engine (issue #20).

Comprehend DetectPiiEntities scans every text the record keeps (the producer's
messages and the correct playback); the agent runs it from Python during record
saves (#26). Only English and Spanish are supported; any other conversation
language flags the record. Only NAME, PHONE, EMAIL and ADDRESS above a
configurable threshold count. Failed scans flag the record: not finding
personal information must not rest on a tool that did not run.

Nothing is ever redacted. Matches keep the matched words (up to 10 context
words either side) for human review (#27); Analytics never reads them and logs
carry types and counts only. A record that turns declined keeps no matches.
"""
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, cast

from fex.models import PiiEntityType, PiiMatch

logger = logging.getLogger("fex.pii")

#: The four entity types the spec asks for; everything else Comprehend reports is ignored.
ENTITY_TYPES: tuple[str, ...] = ("NAME", "PHONE", "EMAIL", "ADDRESS")

#: Comprehend type -> the four spec types. "NAME" is what Comprehend reports for Spanish.
_COMPREHEND_TO_OURS = {
    "PERSON": "NAME", "NAME": "NAME",
    "PHONE": "PHONE", "PHONE_NUMBER": "PHONE",
    "EMAIL": "EMAIL",
    "ADDRESS": "ADDRESS",
}

#: Conversations in these languages are scanned; anything else is unsupported_language.
SCAN_LANGUAGES: tuple[str, ...] = ("en", "es")

DEFAULT_THRESHOLD = 0.8

#: The Comprehend API takes a full code; the record carries the two-letter language.
_LANGUAGE_CODE = {"en": "en", "es": "es"}

TextStatus = Literal["pending", "done", "failed"]  # a text's scan status in the conversation state


@dataclass
class PiiText:
    """One text slated for the record, with its scan status from the conversation state."""

    text: str
    message_at: datetime
    kind: Literal["message", "correct_playback"]
    status: TextStatus = "pending"
    #: Set by the out-of-scope detector (#21): a grievance or other off-topic text adds
    #: nothing to the record, not even a scan.
    out_of_scope: bool = False


@dataclass
class TextOutcome:
    """What this scan pass did with one text."""

    text: PiiText
    status: TextStatus
    error: str | None = None


@dataclass
class PiiResult:
    """The merged PII state for one save: what the record fields should hold."""

    flag: bool = False
    entity_types: list[PiiEntityType] = field(default_factory=list)
    matches: list[PiiMatch] = field(default_factory=list)
    check: Literal["done", "failed", "unsupported_language"] = "done"
    outcomes: list[TextOutcome] = field(default_factory=list)

    def to_fields(self) -> dict:
        """The CompletedRecord fields to apply with model_copy(update=...)."""
        return {
            "pii_flag": self.flag,
            "pii_entity_types": self.entity_types,
            "pii_matches": self.matches,
            "pii_check": self.check,
        }


def default_comprehend(region_name: str = "us-west-2") -> Callable[[str, str], list[dict]]:
    """Comprehend client seam with boto3's real response shape. Imported lazily so tests
    stay credential-free; #26 wires this into the save path."""
    import boto3

    client = boto3.client("comprehend", region_name=region_name)

    def scan(text: str, language: str) -> list[dict]:
        resp = client.detect_pii_entities(Text=text, LanguageCode=_LANGUAGE_CODE[language])
        return list(resp["Entities"])

    return scan


def context_window(text: str, begin: int, end: int, words: int = 10) -> str:
    """Up to `words` tokens before and after the [begin, end) span, whitespace-joined."""
    tokens = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    first = next(i for i, (s, e) in enumerate(tokens) if s <= begin < e)
    last = next(i for i, (s, e) in enumerate(tokens) if s < end <= e)  # spans >= 1 token
    lo = max(0, first - words)
    hi = min(len(tokens), last + words + 1)
    return " ".join(_cut_words(text, [tokens[i] for i in range(lo, hi)]))


def _cut_words(text: str, spans: list[tuple[int, int]]) -> list[str]:
    """The words at the given [start, end) spans. Tokens stay whole: a cut word would
    turn a match's context into a different word."""
    return [text[s:e] for s, e in spans]


def _merge(prior: list[str], extra: list[str]) -> list[str]:
    seen = list(prior)
    for t in extra:
        if t not in seen:
            seen.append(t)
    return seen


def scan_texts(
    texts: list[PiiText],
    language: str,
    client: Callable[[str, str], list[dict]],
    threshold: float = DEFAULT_THRESHOLD,
    prior_flag: bool = False,
    prior_entity_types: list[PiiEntityType] | None = None,
    prior_matches: list[PiiMatch] | None = None,
) -> PiiResult:
    """Scan every not-yet-done, in-record text and merge into the record's PII state.

    - Done texts are never scanned again; failed and pending ones are.
    - Out-of-scope texts add nothing: no scan, no status, no match.
    - A hit sets pii_flag and keeps an entry in pii_matches; scores below the
      threshold do not.
    - A failed call sets pii_flag: a scan that did not run finds nothing.
    - Languages other than en/es flag the record without scanning anything.
    """
    if language not in SCAN_LANGUAGES:
        logger.warning("pii scan: language %r unsupported, flagging record", language)
        return PiiResult(flag=True, check="unsupported_language")

    types = list(prior_entity_types or [])
    matches = list(prior_matches or [])
    outcomes: list[TextOutcome] = []
    hits = 0

    for t in texts:
        if t.out_of_scope:
            continue  # adds nothing to the record, not even a scan error
        if t.status == "done":
            continue  # scanned once, never rescanned
        try:
            entities = client(t.text, language)
        except Exception:
            t.status = "failed"
            outcomes.append(TextOutcome(text=t, status="failed", error="scan failed"))
            logger.warning("pii scan: 1 text failed, leaving the scan failed", exc_info=True)
            continue
        t.status = "done"
        outcomes.append(TextOutcome(text=t, status="done"))
        for e in entities:
            ours = _COMPREHEND_TO_OURS.get(e.get("Type", ""))
            if ours is None:
                continue
            if float(e.get("Score", 0.0)) < threshold:
                continue
            hits += 1
            if ours not in types:
                types.append(cast(PiiEntityType, ours))
            matches.append(PiiMatch(
                entity_type=cast(PiiEntityType, ours),
                text=t.text[e["BeginOffset"]:e["EndOffset"]],
                context=context_window(t.text, e["BeginOffset"], e["EndOffset"]),
                message_at=t.message_at,
            ))

    failed_count = sum(1 for o in outcomes if o.status == "failed")
    if hits or failed_count:
        logger.warning("pii scan: flag; types=%s hits=%d failed_texts=%d", types, hits, failed_count)
    failed = any(t.status == "failed" for t in texts if not t.out_of_scope)
    check = "failed" if failed else "done"
    return PiiResult(
        flag=prior_flag or hits > 0 or failed,
        entity_types=types,
        matches=matches,
        check=check,
        outcomes=outcomes,
    )