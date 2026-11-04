"""Out-of-scope detection (issue #21). Spec: docs/specs/21-out-of-scope.md.

One function decides whether a producer's message is in scope: it takes the message and the current step
and returns a verdict with a short reason code. Handlers and tools never classify requests themselves.

How it decides is "Not decided" in the spec, so the engine takes it as a plug-in. The default
(`always_in_scope`) treats every message as in scope; tests use a fake.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

# Out-of-scope reasons named in the spec. Each has fixed decline text in conversation/copy.py.
OutOfScopeReason = Literal["certification_status", "grievance", "other_producer_data"]


@dataclass(frozen=True)
class ScopeVerdict:
    in_scope: bool
    reason: OutOfScopeReason | None = None


ScopeCheck = Callable[[str, str], ScopeVerdict]


def always_in_scope(text: str, step: str) -> ScopeVerdict:
    """Placeholder until the detection method is decided (spec: Not decided)."""
    return ScopeVerdict(in_scope=True)
