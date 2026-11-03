"""Data models for climate connectors.

Geometry (Location, BBox) and time (DateRange) are defined once in the shared
`common` package and re-exported here, so existing imports such as
`from climate.models import Location, DateRange` keep working while every
connector shares a single definition.

The climate-specific series types (RainfallSeries, ClimateSeries) live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

# Shared, single-source-of-truth models.
from common.geo import BBox, Location
from common.time import DateRange

__all__ = [
    "Location",
    "BBox",
    "DateRange",
    "RainfallSeries",
    "ClimateSeries",
]


@dataclass
class RainfallSeries:
    """A daily rainfall time series (mm/day) for one location."""

    location: Location
    source: str  # "CHIRPS"
    dates: List[date] = field(default_factory=list)
    values_mm: List[Optional[float]] = field(default_factory=list)

    def total_mm(self) -> float:
        """Total rainfall over the series, ignoring missing values."""
        return sum(v for v in self.values_mm if v is not None)

    def to_records(self) -> List[dict]:
        return [
            {"date": d.isoformat(), "rainfall_mm": v}
            for d, v in zip(self.dates, self.values_mm)
        ]


@dataclass
class ClimateSeries:
    """A climate variable time series from a reanalysis source (e.g. ERA5)."""

    location: Location
    source: str  # "ERA5"
    variable: str  # e.g. "2m_temperature" or "total_precipitation"
    unit: str  # e.g. "K", "m"
    dates: List[date] = field(default_factory=list)
    values: List[Optional[float]] = field(default_factory=list)

    def to_records(self) -> List[dict]:
        return [
            {"date": d.isoformat(), self.variable: v}
            for d, v in zip(self.dates, self.values)
        ]
