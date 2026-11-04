"""Regional fact table: what the open data shows for a producer's region and crop (issue #8).

Sources:
  - CHIRPS v2.0 daily rainfall, read through SERVIR ClimateSERV
  - WRI Aqueduct 4.0 baseline and projected water stress, read from WRI's public feature service
  - World Bank Commodity Price Data ("Pink Sheet"), monthly benchmark prices

Nothing calls these services at runtime. Building the table has two steps:

    PYTHONPATH=src uv run python -m fx_data.regional fetch   # network, ~15 min: writes regional_sources.json
    PYTHONPATH=src uv run python -m fx_data.regional build   # offline: writes regional_facts.json

Both JSON files ship inside the package. `RegionalFacts.load()` reads the facts at runtime.

Each region is represented by one point near its centre (admin-1 centroid). Values describe that
point, not the whole region, so climate and water facts carry strength "nearest". Prices are global
benchmarks, not farm-gate prices, so they carry strength "limited".
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from fx_data.text import normalize

HERE = Path(__file__).parent
SOURCES_PATH = HERE / "regional_sources.json"
FACTS_PATH = HERE / "regional_facts.json"

# ---------------------------------------------------------------------------------------------
# Regions: (country, region) -> representative point near the region's centre.
# Country and region names follow the FTUSA sample data. Extend this table to add regions.
# ---------------------------------------------------------------------------------------------
REGIONS: dict[tuple[str, str], tuple[float, float]] = {
    ("Brazil", "Amazonas"): (-3.42, -65.86),
    ("Brazil", "Minas Gerais"): (-18.51, -44.56),
    ("Brazil", "Piaui"): (-7.72, -42.73),
    ("Brazil", "Sao Paulo"): (-22.30, -48.60),
    ("Colombia", "Antioquia"): (6.55, -75.83),
    ("Colombia", "Caldas"): (5.30, -75.27),
    ("Colombia", "Cauca"): (2.44, -76.61),
    ("Colombia", "Cesar"): (9.34, -73.65),
    ("Colombia", "Huila"): (2.54, -75.53),
    ("Colombia", "Norte de Santander"): (7.95, -72.90),
    ("Colombia", "Risaralda"): (5.31, -75.99),
    ("Colombia", "Tolima"): (4.09, -75.15),
    ("Colombia", "Valle del Cauca"): (3.80, -76.52),
    ("Costa Rica", "Alajuela"): (10.39, -84.42),
    ("Costa Rica", "San Jose"): (9.83, -84.07),
    ("Côte d'Ivoire", "Bas-Sassandra"): (5.47, -6.62),
    ("Côte d'Ivoire", "Goh-Djiboua"): (5.88, -5.57),
    ("Côte d'Ivoire", "Zanzan"): (8.60, -3.20),
    ("Ecuador", "Cotopaxi"): (-0.84, -78.66),
    ("Ecuador", "El Oro"): (-3.42, -79.80),
    ("Ethiopia", "YeDebub Biheroch Bihereseboch na Hizboch"): (6.50, 37.00),
    ("Guatemala", "Guatemala"): (14.63, -90.51),
    ("Guatemala", "Huehuetenango"): (15.32, -91.47),
    ("Guatemala", "Jalapa"): (14.63, -89.99),
    ("Guatemala", "Quiche"): (15.03, -91.15),
    ("Guatemala", "Solola"): (14.77, -91.18),
    ("Honduras", "Copan"): (14.85, -88.90),
    ("Honduras", "Intibuca"): (14.32, -88.17),
    ("Honduras", "La Paz"): (14.32, -87.68),
    ("Honduras", "Lempira"): (14.59, -88.57),
    ("Honduras", "Ocotepeque"): (14.43, -89.18),
    ("India", "Assam"): (26.20, 92.94),
    ("India", "Kerala"): (10.85, 76.27),
    ("India", "Tamil Nadu"): (11.13, 78.66),
    ("Indonesia", "Aceh"): (4.70, 96.75),
    ("Indonesia", "Bali"): (-8.34, 115.09),
    ("Kenya", "Kericho"): (-0.37, 35.29),
    ("Mexico", "Chiapas"): (16.75, -92.63),
    ("Mexico", "Guanajuato"): (21.02, -101.26),
    ("Mexico", "Michoacan de Ocampo"): (19.57, -101.71),
    ("Mexico", "Sinaloa"): (24.80, -107.40),
    ("Mexico", "Sonora"): (29.30, -110.33),
    ("Nicaragua", "Boaco"): (12.47, -85.66),
    ("Nicaragua", "Jinotega"): (13.09, -86.00),
    ("Nicaragua", "Madriz"): (13.47, -86.46),
    ("Nicaragua", "Masaya"): (11.97, -86.09),
    ("Peru", "Amazonas"): (-5.08, -78.00),
    ("Peru", "Ancash"): (-9.53, -77.53),
    ("Peru", "Cajamarca"): (-7.16, -78.51),
    ("Peru", "Junin"): (-11.54, -74.95),
    ("Peru", "Lambayeque"): (-6.37, -79.84),
    ("Peru", "Pasco"): (-10.36, -75.35),
    ("Peru", "San Martin"): (-6.48, -76.37),
    ("Rwanda", "Nord"): (-1.50, 29.75),
    ("Rwanda", "Ville de Kigali"): (-1.95, 30.06),
    ("Sri Lanka", "Central Province"): (7.29, 80.64),
}

# Rainfall: compare the two most recent complete years with the ten years before them.
RECENT_YEARS = (2024, 2025)
BASELINE_YEARS = tuple(range(2014, 2024))
MAX_MISSING_DAYS_PER_YEAR = 10

# Prices: crop keyword (as in the sample data's product categories) -> Pink Sheet series.
PRICE_SERIES = {
    "coffee": "Coffee, Arabica",
    "cocoa": "Cocoa",
    "bananas": "Banana, US",
}
PRICE_BASELINE_YEARS = 5

SOURCE_CHIRPS = "CHIRPS v2.0 rainfall (Climate Hazards Center, via SERVIR ClimateSERV)"
SOURCE_AQUEDUCT = "WRI Aqueduct 4.0 water risk atlas"
SOURCE_PINK_SHEET = "World Bank Commodity Price Data (Pink Sheet)"

CHIRPS_URL = "https://climateserv.servirglobal.net/chirps"
AQUEDUCT_URL = ("https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/"
                "aqueduct_water_risk/FeatureServer")
# The Pink Sheet workbook moves to a new folder each year; update this when it does.
PINK_SHEET_URL = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
                  "related/CMO-Historical-Data-Monthly.xlsx")

PROJECTION_YEARS = ("30", "50", "80")  # Aqueduct field codes for 2030, 2050, 2080


# ---------------------------------------------------------------------------------------------
# Fetch (network). Only run during preparation.
# ---------------------------------------------------------------------------------------------

# Some servers (the World Bank's) refuse Python's default user agent with 403 Forbidden.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; fair-exchange-data/0.1)"}


def _open(url: str, timeout: float):
    return urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=timeout)


def _get_json(url: str, params: dict, timeout: float = 90.0, retries: int = 3) -> object:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with _open(full, timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - public services are flaky; retry then report
            last = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"request failed after {retries} attempts: {url}: {last}")


def _first(value: object) -> object:
    return value[0] if isinstance(value, list) and value else value


def fetch_chirps_annual(lat: float, lon: float) -> dict:
    """Annual rainfall totals (mm) for a small box around the point, one value per year."""
    pad = 0.05
    box = {"type": "Polygon", "coordinates": [[[lon - pad, lat - pad], [lon + pad, lat - pad],
                                              [lon + pad, lat + pad], [lon - pad, lat + pad],
                                              [lon - pad, lat - pad]]]}
    first_year, last_year = min(BASELINE_YEARS), max(RECENT_YEARS)
    request_id = _first(_get_json(f"{CHIRPS_URL}/submitDataRequest/", {
        "datatype": 0, "intervaltype": 0, "operationtype": 5,
        "begintime": f"01/01/{first_year}", "endtime": f"12/31/{last_year}",
        "dateType_Category": "default", "isZip_CurrentDataType": "false",
        "geometry": json.dumps(box),
    }))
    deadline = time.monotonic() + 600
    while float(_first(_get_json(f"{CHIRPS_URL}/getDataRequestProgress/", {"id": request_id})) or 0) < 100:
        if time.monotonic() > deadline:
            raise RuntimeError(f"ClimateSERV request {request_id} timed out")
        time.sleep(3)
    data = _get_json(f"{CHIRPS_URL}/getDataFromRequest/", {"id": request_id})
    totals: dict[str, float] = defaultdict(float)
    days: dict[str, int] = defaultdict(int)
    for point in data.get("data", []):
        value = point.get("value")
        value = value.get("avg") if isinstance(value, dict) else value
        if value is None or float(value) <= -9000:
            continue
        year = str(point["year"])
        totals[year] += float(value)
        days[year] += 1
    return {year: {"total_mm": round(totals[year], 1), "days": days[year]} for year in sorted(totals)}


def _aqueduct_point(layer: int, lat: float, lon: float, fields: str) -> dict:
    payload = _get_json(f"{AQUEDUCT_URL}/{layer}/query", {
        "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "outFields": fields, "returnGeometry": "false", "f": "json",
    })
    if "error" in payload:
        raise RuntimeError(f"Aqueduct error: {payload['error']}")
    features = payload.get("features") or []
    return features[0]["attributes"] if features else {}


def fetch_aqueduct(lat: float, lon: float) -> dict:
    baseline = _aqueduct_point(1, lat, lon, "pfaf_id,bws_label,bws_score")
    future_fields = ",".join(f"bau{y}_ws_x_{s}" for y in PROJECTION_YEARS for s in ("l", "s"))
    future = _aqueduct_point(0, lat, lon, future_fields)
    return {
        "basin_id": baseline.get("pfaf_id"),
        "baseline_label": baseline.get("bws_label"),
        "baseline_score": baseline.get("bws_score"),
        "bau": {f"20{y}": {"label": future.get(f"bau{y}_ws_x_l"), "score": future.get(f"bau{y}_ws_x_s")}
                for y in PROJECTION_YEARS},
    }


def fetch_pink_sheet() -> dict:
    """Monthly prices for the series in PRICE_SERIES, from the Pink Sheet workbook."""
    from openpyxl import load_workbook

    with _open(PINK_SHEET_URL, 120) as resp:
        workbook = load_workbook(io.BytesIO(resp.read()), read_only=True, data_only=True)
    sheet = workbook["Monthly Prices"]
    rows = list(sheet.iter_rows(values_only=True))
    updated = next((str(r[0]) for r in rows[:6] if r and isinstance(r[0], str) and "Updated" in r[0]), "")
    header_index = next(i for i, r in enumerate(rows) if r and "Cocoa" in r)
    header, units = rows[header_index], rows[header_index + 1]
    series = {}
    for name in PRICE_SERIES.values():
        col = header.index(name)
        monthly = {str(r[0]): float(r[col]) for r in rows[header_index + 2:]
                   if r and r[0] and isinstance(r[col], (int, float))}
        series[name] = {"unit": str(units[col]).strip("()"), "monthly": monthly}
    return {"updated": updated, "url": PINK_SHEET_URL, "series": series}


CACHE_DIR = HERE.parents[1] / ".cache" / "regional"  # data/.cache/regional, git-ignored


def fetch(workers: int = 4) -> dict:
    """Fetch every region. Each finished region is cached, so an interrupted run resumes."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def one(item):
        (country, region), (lat, lon) = item
        cache = CACHE_DIR / f"{normalize(country)}--{normalize(region)}.json".replace(" ", "_").replace("'", "")
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        record = {"country": country, "region": region, "lat": lat, "lon": lon}
        for key, func in (("chirps", fetch_chirps_annual), ("aqueduct", fetch_aqueduct)):
            try:
                record[key] = func(lat, lon)
            except Exception as exc:  # noqa: BLE001 - keep going; the gap is visible in the output
                record[key] = None
                record[f"{key}_error"] = str(exc)
        if record["chirps"] is not None and record["aqueduct"] is not None:
            cache.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        print(f"  fetched {region}, {country}", file=sys.stderr, flush=True)
        return record

    with ThreadPoolExecutor(max_workers=workers) as pool:
        regions = list(pool.map(one, sorted(REGIONS.items())))
    return {
        "fetched_at": datetime.now(timezone.utc).date().isoformat(),
        "regions": regions,
        "prices": fetch_pink_sheet(),
    }


# ---------------------------------------------------------------------------------------------
# Build (offline): sources -> facts
# ---------------------------------------------------------------------------------------------

def _fact(text: str, source: str, metric: str, value, unit: str | None, period: str, strength: str) -> dict:
    return {"text": text, "source": source, "metric": metric, "value": value, "unit": unit,
            "period": period, "strength": strength}


def _band(label: str | None) -> str | None:
    """'Low - Medium (10-20%)' -> 'low to medium (10-20%)'. Aqueduct writes labels inconsistently."""
    if not label:
        return None
    text = " ".join(label.replace(" - ", "-").split())
    text = text.replace("Low-medium", "Low-Medium").replace("Medium-high", "Medium-High")
    return text.replace("Low-Medium", "low to medium").replace("Medium-High", "medium to high").lower()


def _climate_facts(record: dict) -> list[dict]:
    place = f"near the centre of {record['region']}, {record['country']}"
    facts = []
    chirps = record.get("chirps") or {}
    complete = {int(y): v["total_mm"] for y, v in chirps.items()
                if v["days"] >= (366 if int(y) % 4 == 0 else 365) - MAX_MISSING_DAYS_PER_YEAR}
    if all(y in complete for y in RECENT_YEARS + BASELINE_YEARS):
        recent = sum(complete[y] for y in RECENT_YEARS) / len(RECENT_YEARS)
        baseline = sum(complete[y] for y in BASELINE_YEARS) / len(BASELINE_YEARS)
        if baseline > 0:
            pct = round((recent - baseline) / baseline * 100, 1)
            direction = "below" if pct < 0 else "above"
            r0, r1, b0, b1 = RECENT_YEARS[0], RECENT_YEARS[-1], BASELINE_YEARS[0], BASELINE_YEARS[-1]
            facts.append(_fact(
                f"Rainfall {place} averaged {recent:,.0f} mm a year in {r0}-{r1}, "
                f"{abs(pct)}% {direction} the {b0}-{b1} average of {baseline:,.0f} mm.",
                SOURCE_CHIRPS, "rainfall_change_pct", pct, "%", f"{b0}-{r1}", "nearest"))
    water = record.get("aqueduct") or {}
    baseline_band = _band(water.get("baseline_label"))
    if baseline_band:
        facts.append(_fact(
            f"Baseline water stress in the river basin {place} is {baseline_band}.",
            SOURCE_AQUEDUCT, "baseline_water_stress", water.get("baseline_score"), "score 0-5",
            "1979-2019 baseline", "nearest"))
    projected = {y: _band(v.get("label")) for y, v in (water.get("bau") or {}).items() if v.get("label")}
    if {"2030", "2050"} <= projected.keys():
        facts.append(_fact(
            f"If current trends continue (business as usual), water stress there is projected to be "
            f"{projected['2030']} by 2030 and {projected['2050']} by 2050.",
            SOURCE_AQUEDUCT, "projected_water_stress_2050", (water["bau"]["2050"] or {}).get("score"),
            "score 0-5", "2030-2050 projection", "nearest"))
    return facts


def _month_label(key: str) -> str:
    year, month = key.split("M")
    return date(int(year), int(month), 1).strftime("%B %Y")


def _price_facts(prices: dict) -> dict[str, list[dict]]:
    out = {}
    for crop, name in PRICE_SERIES.items():
        series = prices["series"][name]
        monthly, unit = series["monthly"], series["unit"].replace("$", "US$")
        latest = max(monthly)
        year, month = latest.split("M")
        year_ago = f"{int(year) - 1}M{month}"
        start = f"{int(year) - PRICE_BASELINE_YEARS}M{month}"
        window = [v for k, v in monthly.items() if start < k <= latest]
        value = monthly[latest]
        facts = []
        if year_ago in monthly:
            change = round((value - monthly[year_ago]) / monthly[year_ago] * 100, 1)
            direction = "lower" if change < 0 else "higher"
            facts.append(_fact(
                f"The world benchmark price for {name.lower()} averaged {unit.split('/')[0]} {value:.2f} "
                f"per {unit.split('/')[1]} in {_month_label(latest)}, {abs(change)}% {direction} than a year "
                f"earlier. This is an international market price, not a farm-gate price.",
                f"{SOURCE_PINK_SHEET}: {name}", "benchmark_price_change_pct", change, "%",
                f"{_month_label(year_ago)} to {_month_label(latest)}", "limited"))
        if len(window) >= 12 * PRICE_BASELINE_YEARS - 1:
            avg = sum(window) / len(window)
            facts.append(_fact(
                f"Over the past {PRICE_BASELINE_YEARS} years the {name.lower()} benchmark averaged "
                f"{unit.split('/')[0]} {avg:.2f} per {unit.split('/')[1]}, so the latest price is "
                f"{abs(round((value - avg) / avg * 100))}% {'below' if value < avg else 'above'} that average.",
                f"{SOURCE_PINK_SHEET}: {name}", "benchmark_price_vs_5yr_avg_pct",
                round((value - avg) / avg * 100, 1), "%",
                f"{_month_label(start)} to {_month_label(latest)}", "limited"))
        out[crop] = facts
    return out


def build(sources: dict) -> dict:
    regions = []
    for record in sources["regions"]:
        regions.append({"country": record["country"], "region": record["region"],
                        "lat": record["lat"], "lon": record["lon"], "facts": _climate_facts(record)})
    return {
        "description": "Pre-extracted regional facts for the regional-context tool. Built offline from "
                       "regional_sources.json; never fetched at runtime.",
        "sources_fetched_at": sources["fetched_at"],
        "prices_updated": sources["prices"]["updated"],
        "regions": regions,
        "prices": _price_facts(sources["prices"]),
    }


# ---------------------------------------------------------------------------------------------
# Lookup (runtime)
# ---------------------------------------------------------------------------------------------

@dataclass
class RegionalAnswer:
    matched: bool
    match_level: str  # "region", "country", or "none"
    facts: list[dict]
    note: str | None = None

    def as_dict(self) -> dict:
        return {"matched": self.matched, "match_level": self.match_level, "facts": self.facts,
                "note": self.note}


class RegionalFacts:
    """Read-only lookup over regional_facts.json."""

    def __init__(self, table: dict):
        self._table = table
        self._regions = {(normalize(r["country"]), normalize(r["region"])): r for r in table["regions"]}

    @classmethod
    def load(cls, path: Path = FACTS_PATH) -> "RegionalFacts":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def price_facts(self, crop: str | None) -> list[dict]:
        """Benchmark price facts for a crop field such as 'Coffee' or 'Cocoa;Coffee'."""
        out = []
        for part in (normalize(p) for p in (crop or "").split(";")):
            key = "bananas" if part in ("banana", "bananas") else part
            for fact in self._table["prices"].get(key, []):
                if fact not in out:
                    out.append(fact)
        return out

    def lookup(self, country: str, region: str | None, crop: str | None) -> RegionalAnswer:
        """Facts for a producer's own country, region and crop. Never guesses another region."""
        record = self._regions.get((normalize(country), normalize(region)))
        prices = self.price_facts(crop)
        if record:
            return RegionalAnswer(True, "region", record["facts"] + prices)
        note = (f"No regional climate data is pre-loaded for {region or 'an unknown region'}, {country}. "
                "Only crop price benchmarks are available." if prices else
                f"No regional data is pre-loaded for {region or 'an unknown region'}, {country}.")
        return RegionalAnswer(bool(prices), "country" if prices else "none", prices, note)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=["fetch", "build"])
    args = parser.parse_args(argv)
    if args.step == "fetch":
        sources = fetch()
        SOURCES_PATH.write_text(json.dumps(sources, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {SOURCES_PATH}", file=sys.stderr)
    else:
        sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        facts = build(sources)
        FACTS_PATH.write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        n = sum(len(r["facts"]) for r in facts["regions"])
        print(f"wrote {FACTS_PATH}: {len(facts['regions'])} regions, {n} regional facts", file=sys.stderr)


if __name__ == "__main__":
    main()
