"""Geometry models shared by all connectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Location:
    """A producer location as a lat/lon point.

    Latitude is in [-90, 90], longitude in [-180, 180].
    """

    lat: float
    lon: float
    name: Optional[str] = None

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError(f"lat out of range [-90, 90]: {self.lat}")
        if not -180.0 <= self.lon <= 180.0:
            raise ValueError(f"lon out of range [-180, 180]: {self.lon}")

    def bbox(self, pad: float = 0.1) -> "BBox":
        """A small bounding box around the point (degrees of padding)."""
        return BBox(
            min_lat=max(-90.0, self.lat - pad),
            min_lon=max(-180.0, self.lon - pad),
            max_lat=min(90.0, self.lat + pad),
            max_lon=min(180.0, self.lon + pad),
        )


@dataclass(frozen=True)
class BBox:
    """Bounding box in degrees."""

    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    def as_geojson_polygon(self) -> dict:
        """GeoJSON polygon (used by e.g. the ClimateSERV request payload)."""
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [self.min_lon, self.min_lat],
                    [self.max_lon, self.min_lat],
                    [self.max_lon, self.max_lat],
                    [self.min_lon, self.max_lat],
                    [self.min_lon, self.min_lat],
                ]
            ],
        }
