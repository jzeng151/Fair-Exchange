"""PII flagging (issue #20): scan the producer's own text with Amazon Comprehend DetectPiiEntities.

Spec: docs/specs/20-pii-flagging.md.
  - Scans the producer's messages and correct_playback text, in English and Spanish. FEX's own text is never scanned.
  - Looks only for NAME, PHONE, EMAIL and ADDRESS above a confidence threshold (config, default 0.8).
  - Any hit, a Comprehend error, or an unsupported language flags the record. Nothing is ever redacted.
  - A failed check must never read as "no PII": the flag stays set for the life of the conversation.
Logs carry entity types and counts only, never the matched text.
"""
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from fex.models import PiiEntityType, PiiMatch

log = logging.getLogger(__name__)

DEFAULT_PII_THRESHOLD = 0.8
SUPPORTED_LANGUAGES = ("en", "es")
WANTED_TYPES: frozenset[str] = frozenset({"NAME", "PHONE", "EMAIL", "ADDRESS"})
_CONTEXT_WORDS = 10  # about this many words either side of a match, from the producer's text

# The Comprehend client only needs this one method; a stub with the same shape is enough for tests.
ComprehendClient = Callable[..., dict]


@dataclass
class ScanResult:
    """What a scan of one text produced. `ok` is False on a Comprehend error (the record is flagged `failed`)."""

    ok: bool
    matches: list[PiiMatch] = field(default_factory=list)


def _context(text: str, begin: int, end: int) -> str:
    """About 10 words either side of the match, from the producer's own text."""
    before = text[:begin].split()[-_CONTEXT_WORDS:]
    after = text[end:].split()[:_CONTEXT_WORDS]
    middle = text[begin:end]
    return " ".join([*before, middle, *after]).strip()


class PiiScanner:
    """Wraps a Comprehend client. Scans one text at a time so a per-text status can be tracked (#20)."""

    def __init__(self, client, *, threshold: float = DEFAULT_PII_THRESHOLD) -> None:
        self._client = client
        self.threshold = threshold

    def scan(self, text: str, language: str, message_at) -> ScanResult:
        """Scan one producer text. Returns matches above the threshold, or ok=False if Comprehend errored.

        The caller must only pass a supported language (en or es); unsupported languages are handled by the
        flagger, which never calls Comprehend for them.
        """
        try:
            response = self._client.detect_pii_entities(Text=text, LanguageCode=language)
        except Exception:  # noqa: BLE001 - any Comprehend error flags the record; it must not read as clean
            log.warning("comprehend detect_pii_entities failed; record will be flagged")
            return ScanResult(ok=False)
        matches: list[PiiMatch] = []
        for entity in response.get("Entities", []):
            kind = entity.get("Type")
            if kind not in WANTED_TYPES or entity.get("Score", 0.0) < self.threshold:
                continue
            begin, end = entity.get("BeginOffset", 0), entity.get("EndOffset", 0)
            matches.append(PiiMatch(entity_type=kind, text=text[begin:end],  # type: ignore[arg-type]
                                    context=_context(text, begin, end), message_at=message_at))
        return ScanResult(ok=True, matches=matches)


# ----------------------------------------------------------------------------- per-conversation flagging

@dataclass
class ProducerText:
    """One piece of text the producer typed, with the position it holds in the conversation history."""

    index: int
    text: str
    at: object  # datetime; kept loose so callers need not import datetime here


@dataclass
class PiiOutcome:
    """The accumulated PII state after a scan: the record's fields plus the per-text statuses to persist."""

    flag: bool
    entity_types: list[PiiEntityType]
    matches: list[PiiMatch]
    check: str  # done | failed | unsupported_language
    statuses: dict[int, str]  # history index -> pending | done | done_hit | failed | unsupported


def flag_pii(
    texts: Sequence[ProducerText],
    *,
    language: str,
    prior: PiiOutcome,
    scanner: PiiScanner | None,
) -> PiiOutcome:
    """Fold a scan of the producer's texts into the PII state carried from earlier saves.

    Scans every text that is `pending` or `failed`; a text already done is never scanned again. Matches and
    flags accumulate on top of `prior` and never regress: once flagged, the record stays flagged. The caller
    excludes out-of-scope texts before calling (#21), so nothing from them is ever scanned or kept.
    """
    statuses = dict(prior.statuses)
    matches = list(prior.matches)

    # An unsupported language flags the record without calling Comprehend; en and es are scanned.
    if language not in SUPPORTED_LANGUAGES:
        for t in texts:
            statuses[t.index] = "unsupported"
        return PiiOutcome(flag=True, entity_types=prior.entity_types, matches=prior.matches,
                          check="unsupported_language", statuses=statuses)

    if scanner is None:  # records-less local runs: nothing to scan with
        return PiiOutcome(flag=prior.flag, entity_types=prior.entity_types, matches=matches,
                          check=prior.check, statuses=statuses)

    error = False
    for t in texts:
        if statuses.get(t.index) in ("done", "done_hit"):
            continue  # a text marked done is never scanned again
        result = scanner.scan(t.text, language, t.at)
        if not result.ok:
            statuses[t.index] = "failed"
            error = True
            continue
        statuses[t.index] = "done_hit" if result.matches else "done"
        matches.extend(result.matches)

    any_failed = any(s == "failed" for s in statuses.values())
    check = "failed" if any_failed else "done"
    flag = prior.flag or error or bool(matches) or any_failed
    return PiiOutcome(flag=flag, entity_types=_ordered_types(matches), matches=matches,
                      check=check, statuses=statuses)


EMPTY = PiiOutcome(flag=False, entity_types=[], matches=[], check="done", statuses={})

_TYPE_ORDER = ("NAME", "PHONE", "EMAIL", "ADDRESS")


def _ordered_types(matches: Sequence[PiiMatch]) -> list[PiiEntityType]:
    present = {m.entity_type for m in matches}
    return [t for t in _TYPE_ORDER if t in present]  # type: ignore[misc]


__all__ = ["DEFAULT_PII_THRESHOLD", "EMPTY", "PiiOutcome", "PiiScanner", "ProducerText", "ScanResult", "flag_pii"]
