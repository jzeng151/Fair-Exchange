"""Regional-context (climate) tool for the Producer Exchange Agent.

Spec-aligned shape:
  - Open data (CHIRPS rainfall, Aqueduct water stress) is PRE-EXTRACTED to a
    static table before the event (see prepare.py); the agent tool never makes a
    live API call at runtime (the Technical Environment doc prohibits runtime
    scraping / live API / Earth Engine calls in the demo).
  - The tool (tool.py) reads only that static table and returns a Pydantic
    result with per-claim citations.
  - Lookups are keyed on (country, region, crop) taken from session context, so
    a tool call cannot return data for a location outside the session.
"""

from .schemas import (
    Citation,
    ClimateClaim,
    RegionalClimateContext,
    RegionKey,
)

__all__ = [
    "RegionKey",
    "Citation",
    "ClimateClaim",
    "RegionalClimateContext",
]
