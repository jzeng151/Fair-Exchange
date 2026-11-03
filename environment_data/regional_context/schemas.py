"""Pydantic schemas for the regional-context climate tool.

These enforce the spec's requirements at the tool boundary:
  - structured tool input/output (Pydantic is the preferred library)
  - every claim carries a citation (grounding/traceability is a success metric)
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RegionKey(BaseModel):
    """Identifies a producer region. Supplied from session context, not the model.

    Matching is done on (country, region, crop). `crop` is optional because some
    synthetic records omit it; when absent we fall back to a country+region match.
    """

    country: str = Field(..., description="Country name as it appears in the producer record")
    region: Optional[str] = Field(None, description="Admin-1 region / state / department")
    crop: Optional[str] = Field(None, description="Product category, e.g. 'Coffee'")

    def normalized(self) -> "RegionKey":
        return RegionKey(
            country=_norm(self.country),
            region=_norm(self.region) if self.region else None,
            crop=_norm(self.crop) if self.crop else None,
        )


class Citation(BaseModel):
    """A source reference attached to a single claim."""

    source: str = Field(..., description="Dataset name, e.g. 'CHIRPS' or 'Aqueduct 4.0'")
    detail: str = Field(..., description="What specifically was read (variable, period, scenario)")
    retrieved: str = Field(..., description="ISO date the value was pre-extracted")
    url: Optional[str] = Field(None, description="Public reference URL for the dataset")


class ClimateClaim(BaseModel):
    """One grounded statement about the region's climate, with its citation."""

    statement: str = Field(..., description="Plain-language insight for the producer")
    metric: str = Field(..., description="Machine name of the metric, e.g. 'rainfall_anomaly_pct'")
    value: Optional[float] = Field(None, description="Numeric value behind the statement")
    unit: Optional[str] = Field(None, description="Unit of value")
    citation: Citation


class RegionalClimateContext(BaseModel):
    """The tool's return payload: the matched region plus cited climate claims."""

    matched: bool = Field(..., description="True if a pre-loaded region matched the key")
    region: RegionKey
    match_level: str = Field(
        "none",
        description="How the match was made: 'country_region_crop', 'country_region', 'country', or 'none'",
    )
    claims: List[ClimateClaim] = Field(default_factory=list)
    note: Optional[str] = Field(
        None, description="Human-readable note, e.g. when no data is pre-loaded for a region"
    )


def _norm(value: str) -> str:
    """Lowercase + strip for case/whitespace-insensitive matching."""
    return value.strip().lower()
