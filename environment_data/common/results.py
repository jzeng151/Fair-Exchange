"""Shared result types for point-lookup connectors.

Climate connectors return time series (see climate/models.py). The soil, water,
and tenure connectors instead answer a question *about a place* — so they share
a simpler "point result" shape: one location, a set of named observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .geo import Location


@dataclass
class PointObservation:
    """A single named value measured/derived at a point.

    Example: name="soil_organic_carbon", value=23.0, unit="g/kg".
    `value` may be None when the source has no data at that pixel/polygon.
    """

    name: str
    value: Optional[Any]
    unit: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {"name": self.name, "value": self.value, "unit": self.unit}
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass
class PointResult:
    """The result of querying one source at one location."""

    location: Location
    source: str  # "SoilGrids", "Aqueduct", "WDPA", "LandMark", "JRC-TMF"
    observations: List[PointObservation] = field(default_factory=list)

    def get(self, name: str) -> Optional[PointObservation]:
        for obs in self.observations:
            if obs.name == name:
                return obs
        return None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "location": {
                "lat": self.location.lat,
                "lon": self.location.lon,
                "name": self.location.name,
            },
            "observations": [o.to_dict() for o in self.observations],
        }
