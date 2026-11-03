"""Runtime regional-context climate tool (Strands @tool).

This is what the agent calls. It:
  - reads ONLY the pre-extracted static table (no live API calls at runtime),
  - matches on (country, region, crop) passed from session context,
  - returns a Pydantic RegionalClimateContext with per-claim citations.

Scope enforcement: the function takes country/region/crop as plain arguments that
the agent populates FROM SESSION CONTEXT. It can only ever return a region that
exists in the pre-loaded table; it cannot fetch arbitrary coordinates or another
producer's location at runtime. (In AgentCore these values should be injected
from the session, not from free-form model output.)

Strands is optional at import time: if the SDK is installed, `regional_climate_tool`
is a real @tool; if not, it is the underlying plain function so the logic can be
unit-tested without the SDK.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

from .schemas import (
    Citation,
    ClimateClaim,
    RegionalClimateContext,
    RegionKey,
)

# Default location of the pre-extracted table (overridable via env for S3/local).
_DEFAULT_TABLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "regional_climate.json",
)


@lru_cache(maxsize=1)
def _load_table(path: str) -> dict:
    """Load and cache the static table. Cached so repeated tool calls are cheap."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _match(table: dict, key: RegionKey) -> tuple[Optional[dict], str]:
    """Find the best region record for the key.

    Returns (record, match_level). crop is currently informational: the climate
    table is keyed on (country, region); crop is carried through for the agent's
    downstream grounding but does not change the climate match.
    """
    k = key.normalized()
    regions = table.get("regions", [])

    # country + region
    if k.region:
        for rec in regions:
            if (
                rec["country"].strip().lower() == k.country
                and rec["region"].strip().lower() == k.region
            ):
                level = "country_region_crop" if k.crop else "country_region"
                return rec, level

    # country only -> return the first region in that country as weak context
    for rec in regions:
        if rec["country"].strip().lower() == k.country:
            return rec, "country"

    return None, "none"


def get_regional_climate(
    country: str,
    region: Optional[str] = None,
    crop: Optional[str] = None,
    table_path: Optional[str] = None,
) -> RegionalClimateContext:
    """Return pre-extracted climate context for a producer's region.

    Args:
        country: Producer country (from session context).
        region: Producer admin-1 region/state (from session context).
        crop: Product category, e.g. "Coffee" (from session context).
        table_path: Override path to the static table (defaults to the bundled one).

    Returns:
        RegionalClimateContext with cited rainfall and water-stress claims. If no
        region is pre-loaded, `matched` is False and `note` explains why — the
        agent should then say it has no regional data rather than inventing any.
    """
    key = RegionKey(country=country, region=region, crop=crop)
    path = table_path or os.getenv("REGIONAL_CLIMATE_TABLE", _DEFAULT_TABLE)

    try:
        table = _load_table(path)
    except FileNotFoundError:
        return RegionalClimateContext(
            matched=False,
            region=key,
            match_level="none",
            note=(
                "No pre-extracted climate table found. Run "
                "`python -m regional_context.prepare` during prep."
            ),
        )

    record, level = _match(table, key)
    if record is None:
        return RegionalClimateContext(
            matched=False,
            region=key,
            match_level="none",
            note=f"No pre-loaded climate data for {region or '(no region)'}, {country}.",
        )

    claims = [
        ClimateClaim(
            statement=c["statement"],
            metric=c["metric"],
            value=c.get("value"),
            unit=c.get("unit"),
            citation=Citation(**c["citation"]),
        )
        for c in record.get("claims", [])
    ]
    note = None
    if level == "country":
        note = (
            f"No exact match for region '{region}'. Returning country-level context "
            f"for {country} from region '{record['region']}'."
        )

    return RegionalClimateContext(
        matched=True,
        region=key,
        match_level=level,
        claims=claims,
        note=note,
    )


# --- Strands tool registration (optional import) ---------------------------
try:
    from strands import tool  # type: ignore

    @tool
    def regional_climate_tool(
        country: str, region: Optional[str] = None, crop: Optional[str] = None
    ) -> dict:
        """Return cited climate context (rainfall trend, water stress) for a
        producer's region. country/region/crop come from the session's producer
        record. Returns insights with per-claim citations; says so when no data
        is pre-loaded for the region.
        """
        return get_regional_climate(country, region, crop).model_dump()

except ImportError:  # Strands not installed in this environment.
    # Fall back to the plain function so logic is usable/testable without the SDK.
    regional_climate_tool = get_regional_climate  # type: ignore
