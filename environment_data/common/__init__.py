"""Shared models used by every data source connector.

These are deliberately dependency-free (stdlib only) so any connector or the
agent layer can import them without pulling in requests/xarray/etc.
"""

from .geo import BBox, Location
from .time import DateRange
from .results import PointObservation, PointResult

__all__ = [
    "Location",
    "BBox",
    "DateRange",
    "PointObservation",
    "PointResult",
]
