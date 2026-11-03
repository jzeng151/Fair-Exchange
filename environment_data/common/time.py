"""Time-range model shared by time-series connectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DateRange:
    """Inclusive start/end date range."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"end {self.end} is before start {self.start}")

    @classmethod
    def parse(cls, start: str, end: str) -> "DateRange":
        """Build from ISO date strings (YYYY-MM-DD)."""
        return cls(date.fromisoformat(start), date.fromisoformat(end))
