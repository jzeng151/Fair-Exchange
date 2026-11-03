"""Command-line smoke test for the climate connectors.

Usage:
    python -m climate.cli chirps --lat -1.95 --lon 30.06 \
        --start 2023-01-01 --end 2023-03-31

    python -m climate.cli era5 --lat -1.95 --lon 30.06 \
        --start 2023-01-01 --end 2023-01-31 --variable 2m_temperature
"""

from __future__ import annotations

import argparse
import json
import sys

# Load config/.env if python-dotenv is available (optional convenience).
try:
    from dotenv import load_dotenv

    load_dotenv("config/.env")
except ImportError:
    pass

from .models import DateRange, Location


def _common_location(args) -> Location:
    return Location(lat=args.lat, lon=args.lon, name=args.name)


def _run_chirps(args) -> int:
    from .chirps import CHIRPSClient

    client = CHIRPSClient()
    series = client.get_rainfall(
        _common_location(args), DateRange.parse(args.start, args.end)
    )
    print(
        json.dumps(
            {
                "source": series.source,
                "location": {"lat": args.lat, "lon": args.lon, "name": args.name},
                "total_mm": round(series.total_mm(), 2),
                "n_days": len(series.dates),
                "sample": series.to_records()[:5],
            },
            indent=2,
        )
    )
    return 0


def _run_era5(args) -> int:
    from .era5 import ERA5Client

    client = ERA5Client()
    series = client.get_series(
        _common_location(args),
        DateRange.parse(args.start, args.end),
        variable=args.variable,
    )
    print(
        json.dumps(
            {
                "source": series.source,
                "variable": series.variable,
                "unit": series.unit,
                "location": {"lat": args.lat, "lon": args.lon, "name": args.name},
                "n_days": len(series.dates),
                "sample": series.to_records()[:5],
            },
            indent=2,
        )
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Climate data smoke test")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("chirps", "era5"):
        p = sub.add_parser(name, help=f"query {name.upper()}")
        p.add_argument("--lat", type=float, required=True)
        p.add_argument("--lon", type=float, required=True)
        p.add_argument("--start", required=True, help="YYYY-MM-DD")
        p.add_argument("--end", required=True, help="YYYY-MM-DD")
        p.add_argument("--name", default=None, help="optional location name")
        if name == "era5":
            p.add_argument(
                "--variable",
                default="2m_temperature",
                choices=["2m_temperature", "total_precipitation"],
            )

    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "chirps":
        return _run_chirps(args)
    if args.command == "era5":
        return _run_era5(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
