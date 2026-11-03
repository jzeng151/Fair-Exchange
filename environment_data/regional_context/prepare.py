"""Pre-extraction: build the static regional climate table BEFORE the event.

Per the Technical Environment doc, open data must be pre-extracted (not called
live at runtime). This script runs ONCE during prep. It:
  1. reads the catalogued producer regions (region_centroids.py),
  2. calls CHIRPS and Aqueduct once per region (this is prep time, not demo time),
  3. derives cited climate claims per region,
  4. writes a static JSON table the runtime tool reads.

Usage:
    python -m regional_context.prepare --out data/regional_climate.json
    python -m regional_context.prepare --out data/regional_climate.json --only colombia

In the real sandbox this JSON would be uploaded to S3 (and optionally registered
in the Glue Data Catalog for Athena). Here it is written locally; the tool reads
from the same path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Reuse the already-verified connectors for the one-time extraction.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from climate import CHIRPSClient  # noqa: E402
from common import DateRange, Location  # noqa: E402
from water import AqueductClient  # noqa: E402

from .region_centroids import all_regions  # noqa: E402

_TODAY = date.today()
_RETRIEVED = _TODAY.isoformat()

# CHIRPS: compare a recent window to a baseline window to flag shifting rainfall.
# Both are the same calendar months to keep the comparison seasonal.
_RECENT_YEARS = 2
_BASELINE_YEARS = 10

_CHIRPS_URL = "https://www.chc.ucsb.edu/data/chirps"
_AQUEDUCT_URL = "https://www.wri.org/data/aqueduct-water-risk-atlas"


def _recent_and_baseline_totals(
    chirps: CHIRPSClient, loc: Location
) -> Tuple[Optional[float], Optional[float]]:
    """Return (recent_annual_mean_mm, baseline_annual_mean_mm) for a location.

    Uses whole calendar years ending last completed year to avoid partial-year
    bias. Returns (None, None) if CHIRPS has no data for the point.
    """
    last_full_year = _TODAY.year - 1
    recent_start = date(last_full_year - _RECENT_YEARS + 1, 1, 1)
    recent_end = date(last_full_year, 12, 31)
    baseline_start = date(last_full_year - _BASELINE_YEARS + 1, 1, 1)
    baseline_end = date(last_full_year, 12, 31)

    recent = chirps.get_rainfall(loc, DateRange(recent_start, recent_end))
    baseline = chirps.get_rainfall(loc, DateRange(baseline_start, baseline_end))

    recent_vals = [v for v in recent.values_mm if v is not None]
    baseline_vals = [v for v in baseline.values_mm if v is not None]
    if not recent_vals or not baseline_vals:
        return None, None

    recent_annual = sum(recent_vals) / _RECENT_YEARS
    baseline_annual = sum(baseline_vals) / _BASELINE_YEARS
    return recent_annual, baseline_annual


def _build_region_record(
    chirps: CHIRPSClient,
    aqueduct: AqueductClient,
    country: str,
    region: str,
    lat: float,
    lon: float,
) -> Dict:
    loc = Location(lat=lat, lon=lon, name=f"{region}, {country}")
    claims: List[Dict] = []

    # --- CHIRPS rainfall anomaly ---
    try:
        recent, baseline = _recent_and_baseline_totals(chirps, loc)
        if recent is not None and baseline is not None and baseline > 0:
            anomaly_pct = round((recent - baseline) / baseline * 100.0, 1)
            direction = "below" if anomaly_pct < 0 else "above"
            claims.append(
                {
                    "statement": (
                        f"Over the last {_RECENT_YEARS} years, annual rainfall in "
                        f"{region} averaged {abs(anomaly_pct)}% {direction} the "
                        f"{_BASELINE_YEARS}-year average."
                    ),
                    "metric": "rainfall_anomaly_pct",
                    "value": anomaly_pct,
                    "unit": "percent",
                    "citation": {
                        "source": "CHIRPS",
                        "detail": (
                            f"Daily rainfall via ClimateSERV; recent "
                            f"{_RECENT_YEARS}-yr vs {_BASELINE_YEARS}-yr annual mean"
                        ),
                        "retrieved": _RETRIEVED,
                        "url": _CHIRPS_URL,
                    },
                }
            )
    except Exception as exc:  # noqa: BLE001 - prep is best-effort per region
        print(f"  ! CHIRPS failed for {region}, {country}: {exc}", file=sys.stderr)

    # --- Aqueduct baseline + projected water stress ---
    try:
        water = aqueduct.get_water_risk(loc)
        baseline_ws = water.get("baseline_water_stress")
        if baseline_ws and baseline_ws.value:
            claims.append(
                {
                    "statement": f"Baseline water stress in {region} is rated '{baseline_ws.value}'.",
                    "metric": "baseline_water_stress",
                    "value": baseline_ws.detail.get("score"),
                    "unit": "category",
                    "citation": {
                        "source": "Aqueduct 4.0",
                        "detail": "Baseline annual water stress (WRI Aqueduct, HydroBASINS L6)",
                        "retrieved": _RETRIEVED,
                        "url": _AQUEDUCT_URL,
                    },
                }
            )
        future_2050 = water.get("water_stress_bau_2050")
        if future_2050 and future_2050.value:
            claims.append(
                {
                    "statement": (
                        f"Under a business-as-usual scenario, water stress in {region} "
                        f"is projected to reach '{future_2050.value}' by 2050."
                    ),
                    "metric": "water_stress_bau_2050",
                    "value": future_2050.detail.get("score"),
                    "unit": "category",
                    "citation": {
                        "source": "Aqueduct 4.0",
                        "detail": "Projected water stress, business-as-usual scenario, 2050",
                        "retrieved": _RETRIEVED,
                        "url": _AQUEDUCT_URL,
                    },
                }
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Aqueduct failed for {region}, {country}: {exc}", file=sys.stderr)

    return {
        "country": country,
        "region": region,
        "centroid": {"lat": lat, "lon": lon},
        "claims": claims,
    }


def build_table(only_country: Optional[str] = None) -> Dict:
    chirps = CHIRPSClient()
    aqueduct = AqueductClient()
    regions = all_regions()

    records = []
    for (country, region), (lat, lon) in sorted(regions.items()):
        if only_country and country != only_country.strip().lower():
            continue
        print(f"Extracting {region}, {country} ...", file=sys.stderr)
        records.append(
            _build_region_record(chirps, aqueduct, country, region, lat, lon)
        )

    return {
        "schema_version": 1,
        "generated": datetime.utcnow().isoformat() + "Z",
        "description": (
            "Pre-extracted regional climate context (CHIRPS rainfall anomaly + "
            "Aqueduct water stress) for FTUSA producer regions. Static table read "
            "by the regional-context agent tool; no runtime API calls."
        ),
        "regions": records,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pre-extract regional climate data")
    parser.add_argument(
        "--out", default="data/regional_climate.json", help="output JSON path"
    )
    parser.add_argument(
        "--only", default=None, help="limit to one country (e.g. 'colombia')"
    )
    args = parser.parse_args(argv)

    table = build_table(only_country=args.only)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(table, fh, indent=2, ensure_ascii=False)

    n_regions = len(table["regions"])
    n_claims = sum(len(r["claims"]) for r in table["regions"])
    print(
        f"Wrote {args.out}: {n_regions} regions, {n_claims} cited claims.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
