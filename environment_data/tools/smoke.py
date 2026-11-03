"""Unified smoke-test CLI across every data source.

Usage (from /workshop, with the venv active):
    python -m tools.smoke soilgrids --lat 52.0 --lon 5.1
    python -m tools.smoke aqueduct  --lat -1.3 --lon 36.8
    python -m tools.smoke landmark  --lat -16.9218 --lon -39.2732
    python -m tools.smoke chirps    --lat -1.95 --lon 30.06 --start 2023-01-01 --end 2023-03-31
    python -m tools.smoke era5      --lat -1.95 --lon 30.06 --start 2023-01-01 --end 2023-01-31
    python -m tools.smoke wdpa      --lat -2.33 --lon 34.83      # needs WDPA_TOKEN
    python -m tools.smoke jrc       --lat -3.5  --lon -62.5      # needs Earth Engine

No-auth sources (soilgrids, aqueduct, landmark, chirps) work out of the box.
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from dotenv import load_dotenv

    load_dotenv("config/.env")
except ImportError:
    pass

from common import DateRange, Location


def _loc(args) -> Location:
    return Location(lat=args.lat, lon=args.lon, name=args.name)


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _soilgrids(args) -> int:
    from soil import SoilGridsClient

    _print(SoilGridsClient().get_soil(_loc(args)).to_dict())
    return 0


def _aqueduct(args) -> int:
    from water import AqueductClient

    _print(AqueductClient(scenario=args.scenario).get_water_risk(_loc(args)).to_dict())
    return 0


def _landmark(args) -> int:
    from tenure import LandMarkClient

    _print(LandMarkClient().get_land_tenure(_loc(args)).to_dict())
    return 0


def _wdpa(args) -> int:
    from tenure import WDPAClient

    _print(WDPAClient().get_protected_areas(_loc(args)).to_dict())
    return 0


def _jrc(args) -> int:
    from soil import JRCForestClient

    _print(JRCForestClient().get_forest(_loc(args)).to_dict())
    return 0


def _chirps(args) -> int:
    from climate import CHIRPSClient

    s = CHIRPSClient().get_rainfall(_loc(args), DateRange.parse(args.start, args.end))
    _print(
        {
            "source": s.source,
            "total_mm": round(s.total_mm(), 2),
            "n_days": len(s.dates),
            "sample": s.to_records()[:5],
        }
    )
    return 0


def _era5(args) -> int:
    from climate import ERA5Client

    s = ERA5Client().get_series(
        _loc(args), DateRange.parse(args.start, args.end), variable=args.variable
    )
    _print(
        {
            "source": s.source,
            "variable": s.variable,
            "unit": s.unit,
            "n_days": len(s.dates),
            "sample": s.to_records()[:5],
        }
    )
    return 0


_HANDLERS = {
    "soilgrids": _soilgrids,
    "aqueduct": _aqueduct,
    "landmark": _landmark,
    "wdpa": _wdpa,
    "jrc": _jrc,
    "chirps": _chirps,
    "era5": _era5,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test any data source")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in _HANDLERS:
        p = sub.add_parser(name)
        p.add_argument("--lat", type=float, required=True)
        p.add_argument("--lon", type=float, required=True)
        p.add_argument("--name", default=None)
        if name in ("chirps", "era5"):
            p.add_argument("--start", required=True, help="YYYY-MM-DD")
            p.add_argument("--end", required=True, help="YYYY-MM-DD")
        if name == "era5":
            p.add_argument(
                "--variable",
                default="2m_temperature",
                choices=["2m_temperature", "total_precipitation"],
            )
        if name == "aqueduct":
            p.add_argument(
                "--scenario", default="bau", choices=["bau", "opt", "pes"]
            )
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    return _HANDLERS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
