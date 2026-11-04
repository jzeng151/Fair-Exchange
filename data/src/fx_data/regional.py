"""Regional fact table: what the open data shows for a producer's region and crop (issue #8).

Sources:
  - CHIRPS v2.0 daily rainfall, read through SERVIR ClimateSERV
  - WRI Aqueduct 4.0 baseline and projected water stress, read from WRI's public feature service
  - World Bank Commodity Price Data ("Pink Sheet"), monthly benchmark prices

Nothing calls these services at runtime. Building the table has two steps:

    PYTHONPATH=src uv run python -m fx_data.regional fetch   # network, ~15 min: writes regional_sources.json
    PYTHONPATH=src uv run python -m fx_data.regional build   # offline: writes regional_facts.csv

Both files ship inside the package. `RegionalFacts.load()` reads and validates the CSV at runtime.

Rows follow the #8 spec's columns (`fact_id`, `scope`, `country`, `admin1`, `crop`, `tags`, ...):
  - region rows: one point near the region's centre (admin-1 centroid), so the value describes that
    point; the `comparison` column says so for water stress;
  - country rows: the average of that country's region rows in this table (said in `comparison`);
  - global rows: World Bank benchmark prices, which are world market prices, not farm-gate prices.
The regional-context tool (#15) gives region rows strength "exact", country "nearest", global "limited".
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from fx_data.text import normalize

HERE = Path(__file__).parent
SOURCES_PATH = HERE / "regional_sources.json"
FACTS_PATH = HERE / "regional_facts.csv"

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
# Build (offline): sources -> fact table (CSV, columns per the #8 spec)
# ---------------------------------------------------------------------------------------------

# ISO 3166-1 alpha-2 for the countries in REGIONS (and the producer table's spellings).
COUNTRY_CODES = {
    "Brazil": "BR", "Colombia": "CO", "Costa Rica": "CR", "Côte d'Ivoire": "CI", "Ecuador": "EC",
    "Ethiopia": "ET", "Guatemala": "GT", "Honduras": "HN", "India": "IN", "Indonesia": "ID",
    "Kenya": "KE", "Mexico": "MX", "Nicaragua": "NI", "Peru": "PE", "Rwanda": "RW", "Sri Lanka": "LK",
}
COUNTRY_NAMES = {code: name for name, code in COUNTRY_CODES.items()}
_CODE_BY_KEY = {normalize(name): code for name, code in COUNTRY_CODES.items()}

CROPS = ("coffee", "banana", "cocoa")
CHALLENGE_TAGS = (
    "climate and weather", "water", "soil and land", "market and price", "labor and migration",
    "financial and access to capital", "education", "health", "infrastructure",
    "biodiversity and conservation", "social and community",
)
COLUMNS = ("fact_id", "scope", "country", "admin1", "crop", "tags", "indicator", "value", "unit",
           "comparison", "period", "source_name", "source_url", "extracted_at", "curated")

# Which challenges each indicator speaks to (#8: "each fact mapped to challenge tags").
INDICATOR_TAGS = {
    "rainfall_anomaly_pct": ("climate and weather", "water"),
    "water_stress_score": ("water",),
    "water_stress_score_2050": ("water", "climate and weather"),
    "price_usd_per_kg": ("market and price",),
    "price_vs_5yr_avg_pct": ("market and price",),
}
PRICE_CROPS = {"coffee": "Coffee, Arabica", "cocoa": "Cocoa", "banana": "Banana, US"}  # Pink Sheet series
SOURCE_URLS = {
    "CHIRPS v2.0": "https://www.chc.ucsb.edu/data/chirps",
    "WRI Aqueduct 4.0": "https://www.wri.org/data/aqueduct-global-maps-40-data",
}


def country_code(name: str | None) -> str | None:
    """'Cote d'Ivoire', 'Côte d’Ivoire' and 'Côte d'Ivoire' all give 'CI'."""
    return _CODE_BY_KEY.get(normalize(name))


def normalize_crops(raw: str | None) -> set[str]:
    """'Cocoa;Coffee' -> {'cocoa', 'coffee'}; 'Bananas' -> {'banana'}. Anything else is dropped.
    Stand-in for the reviewed vocabulary mapping table (#7)."""
    out = set()
    for part in (normalize(p) for p in (raw or "").split(";")):
        part = {"bananas": "banana"}.get(part, part)
        if part in CROPS:
            out.add(part)
    return out


def _fact_id(scope: str, country: str, admin1: str, crop: str, indicator: str) -> str:
    key = "|".join((scope, country, admin1, crop, indicator))
    return "RF-" + hashlib.sha1(key.encode()).hexdigest()[:6].upper()


def _row(scope, country, admin1, crop, indicator, value, unit, comparison, period, source_name,
         source_url, extracted_at, curated=False) -> dict:
    return {"fact_id": _fact_id(scope, country, admin1, crop, indicator), "scope": scope, "country": country,
            "admin1": admin1, "crop": crop, "tags": ";".join(INDICATOR_TAGS[indicator]),
            "indicator": indicator, "value": value, "unit": unit, "comparison": comparison, "period": period,
            "source_name": source_name, "source_url": source_url, "extracted_at": extracted_at,
            "curated": "true" if curated else "false"}


def _band(label: str | None) -> str | None:
    """'Low - Medium (10-20%)' -> 'low to medium (10-20%)'. Aqueduct writes labels inconsistently."""
    if not label:
        return None
    text = " ".join(label.replace(" - ", "-").split())
    text = text.replace("Low-medium", "Low-Medium").replace("Medium-high", "Medium-High")
    return text.replace("Low-Medium", "low to medium").replace("Medium-High", "medium to high").lower()


def _month_label(key: str) -> str:
    year, month = key.split("M")
    return date(int(year), int(month), 1).strftime("%B %Y")


def _region_rows(record: dict, extracted: str) -> list[dict]:
    cc, admin1, rows = COUNTRY_CODES[record["country"]], record["region"], []
    chirps = record.get("chirps") or {}
    complete = {int(y): v["total_mm"] for y, v in chirps.items()
                if v["days"] >= (366 if int(y) % 4 == 0 else 365) - MAX_MISSING_DAYS_PER_YEAR}
    if all(y in complete for y in RECENT_YEARS + BASELINE_YEARS):
        recent = sum(complete[y] for y in RECENT_YEARS) / len(RECENT_YEARS)
        baseline = sum(complete[y] for y in BASELINE_YEARS) / len(BASELINE_YEARS)
        if baseline > 0:
            r0, r1, b0, b1 = RECENT_YEARS[0], RECENT_YEARS[-1], BASELINE_YEARS[0], BASELINE_YEARS[-1]
            rows.append(_row("region", cc, admin1, "", "rainfall_anomaly_pct",
                             round((recent - baseline) / baseline * 100, 1), "%",
                             f"vs {b0}-{b1} mean ({recent:,.0f} mm vs {baseline:,.0f} mm a year)", f"{r0}-{r1}",
                             "CHIRPS v2.0", SOURCE_URLS["CHIRPS v2.0"], extracted))
    water = record.get("aqueduct") or {}
    if band := _band(water.get("baseline_label")):
        rows.append(_row("region", cc, admin1, "", "water_stress_score", round(water["baseline_score"], 2),
                         "score 0-5", f"{band}; river basin at the region's centre", "1979-2019",
                         "WRI Aqueduct 4.0", SOURCE_URLS["WRI Aqueduct 4.0"], extracted))
    bau = water.get("bau") or {}
    b30, b50 = _band((bau.get("2030") or {}).get("label")), _band((bau.get("2050") or {}).get("label"))
    if b30 and b50 and (bau["2050"] or {}).get("score") is not None:
        rows.append(_row("region", cc, admin1, "", "water_stress_score_2050", round(bau["2050"]["score"], 2),
                         "score 0-5", f"business-as-usual projection: {b30} by 2030, {b50} by 2050",
                         "2030-2050", "WRI Aqueduct 4.0", SOURCE_URLS["WRI Aqueduct 4.0"], extracted))
    return rows


def _country_rows(region_rows: list[dict]) -> list[dict]:
    """Country rows: the average of that country's region rows in this table, labelled as such."""
    out, groups = [], defaultdict(list)
    for r in region_rows:
        if r["indicator"] in ("rainfall_anomaly_pct", "water_stress_score"):
            groups[(r["country"], r["indicator"])].append(r)
    for (cc, indicator), rows in sorted(groups.items()):
        mean = sum(float(r["value"]) for r in rows) / len(rows)
        first = rows[0]
        out.append(_row("country", cc, "", "", indicator, round(mean, 1 if indicator.endswith("pct") else 2),
                        first["unit"], f"average of {len(rows)} region{'s' if len(rows) > 1 else ''} in this table",
                        first["period"], first["source_name"], first["source_url"], first["extracted_at"]))
    return out


def _price_rows(prices: dict, extracted: str) -> list[dict]:
    rows = []
    for crop, series_name in PRICE_CROPS.items():
        series = prices["series"][series_name]
        monthly = series["monthly"]
        latest = max(monthly)
        year, month = latest.split("M")
        year_ago, start = f"{int(year) - 1}M{month}", f"{int(year) - PRICE_BASELINE_YEARS}M{month}"
        value = monthly[latest]
        name = f"World Bank Pink Sheet ({series_name})"
        if year_ago in monthly:
            change = round((value - monthly[year_ago]) / monthly[year_ago] * 100, 1)
            rows.append(_row("global", "", "", crop, "price_usd_per_kg", round(value, 2), "US$/kg",
                             f"{abs(change)}% {'lower' if change < 0 else 'higher'} than {_month_label(year_ago)}; "
                             "world benchmark, not a farm-gate price", _month_label(latest), name, prices["url"],
                             extracted))
        window = [v for k, v in monthly.items() if start < k <= latest]
        if len(window) >= 12 * PRICE_BASELINE_YEARS - 1:
            avg = sum(window) / len(window)
            rows.append(_row("global", "", "", crop, "price_vs_5yr_avg_pct", round((value - avg) / avg * 100, 1),
                             "%", f"{_month_label(latest)} price vs the {_month_label(start)} to "
                             f"{_month_label(latest)} average of US${avg:.2f}/kg; world benchmark",
                             _month_label(latest), name, prices["url"], extracted))
    return rows


def build(sources: dict) -> list[dict]:
    extracted = sources["fetched_at"]
    region = [r for record in sources["regions"] for r in _region_rows(record, extracted)]
    rows = region + _country_rows(region) + _price_rows(sources["prices"], extracted)
    validate_rows(rows)
    return rows


def write_csv(rows: list[dict], path: Path = FACTS_PATH) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------------------------
# Load + validate (runtime)
# ---------------------------------------------------------------------------------------------

def validate_rows(rows: list[dict]) -> None:
    """Reject rows the #8 spec rules out. Raises ValueError naming the first bad row."""
    seen = set()
    for r in rows:
        fid = r.get("fact_id") or "?"
        def bad(why: str):
            raise ValueError(f"fact {fid}: {why}")
        if fid in seen:
            bad("duplicate fact_id")
        seen.add(fid)
        if r["scope"] not in ("region", "country", "global"):
            bad(f"unknown scope {r['scope']!r}")
        if r["scope"] == "global" and (r["country"] or r["admin1"]):
            bad("global rows have no country or region")
        if r["scope"] != "global" and r["country"] not in COUNTRY_NAMES:
            bad(f"unknown country code {r['country']!r}")
        if (r["scope"] == "region") != bool(r["admin1"]):
            bad("admin1 is set on region rows only")
        if r["crop"] and r["crop"] not in CROPS:
            bad(f"unknown crop {r['crop']!r}")
        tags = [t for t in str(r["tags"]).split(";") if t]
        if not tags or any(t not in CHALLENGE_TAGS for t in tags):
            bad(f"bad tags {r['tags']!r}")
        for col in ("indicator", "unit", "comparison", "period", "source_name", "source_url", "extracted_at"):
            if not str(r.get(col) or "").strip():
                bad(f"empty {col}")
        if str(r["curated"]) not in ("true", "false"):
            bad("curated must be true or false")


INDICATOR_LABELS = {
    "rainfall_anomaly_pct": "rainfall anomaly",
    "water_stress_score": "baseline water stress",
    "water_stress_score_2050": "projected water stress",
    "price_usd_per_kg": "price",
    "price_vs_5yr_avg_pct": "price vs 5-year average",
}


def source_label(row: dict) -> str:
    """`<source_name> [<crop>] <indicator>, <where>, <period>[ (curated stand-in)] [<fact_id>]` (#8 spec),
    e.g. `CHIRPS v2.0 rainfall anomaly, Cauca, Colombia, 2024-2025 [RF-F8C4E1]`."""
    where = (f"{row['admin1']}, {COUNTRY_NAMES[row['country']]}" if row["scope"] == "region"
             else COUNTRY_NAMES[row["country"]] if row["scope"] == "country" else "global")
    what = " ".join(x for x in (row["crop"], INDICATOR_LABELS.get(row["indicator"], row["indicator"])) if x)
    curated = " (curated stand-in)" if str(row["curated"]) == "true" else ""
    return f"{row['source_name']} {what}, {where}, {row['period']}{curated} [{row['fact_id']}]"


def fact_text(row: dict) -> str:
    """A plain sentence with the value, unit, comparison and period."""
    v, ind = float(row["value"]), row["indicator"]
    where = (f"near the centre of {row['admin1']}, {COUNTRY_NAMES[row['country']]}" if row["scope"] == "region"
             else f"across {COUNTRY_NAMES[row['country']]}" if row["scope"] == "country" else "")
    if ind == "rainfall_anomaly_pct":
        # Region rows compare with "vs 2014-2023 mean (...)"; country rows say how they were averaged.
        comparison = row["comparison"]
        baseline = (comparison.removeprefix("vs ") if comparison.startswith("vs ")
                    else f"{BASELINE_YEARS[0]}-{BASELINE_YEARS[-1]} mean ({comparison})")
        return f"Rainfall {where} in {row['period']} was {abs(v)}% {'below' if v < 0 else 'above'} the {baseline}."
    if ind == "water_stress_score":
        return f"Baseline water stress {where} scores {v:.2f} on a 0-5 scale ({row['comparison']}, {row['period']})."
    if ind == "water_stress_score_2050":
        return f"Water stress {where} is projected to score {v:.2f} on a 0-5 scale by 2050 ({row['comparison']})."
    crop = row["crop"]
    if ind == "price_usd_per_kg":
        return f"The world benchmark price for {crop} was US${v:.2f} per kg in {row['period']} ({row['comparison']})."
    if ind == "price_vs_5yr_avg_pct":
        return (f"The world benchmark price for {crop} was {abs(v)}% {'below' if v < 0 else 'above'} its "
                f"5-year average ({row['comparison']}).")
    return f"{ind}: {row['value']} {row['unit']} ({row['comparison']}, {row['period']})."


STRENGTH = {"region": "exact", "country": "nearest", "global": "limited"}
MAX_ITEMS = 8


class RegionalFacts:
    """Read-only lookup over regional_facts.csv, validated when loaded."""

    def __init__(self, rows: list[dict]):
        validate_rows(rows)
        self.rows = rows

    @classmethod
    def load(cls, path: Path = FACTS_PATH) -> "RegionalFacts":
        with open(path, encoding="utf-8", newline="") as fh:
            return cls(list(csv.DictReader(fh)))

    def lookup(self, country: str | None, admin1: str | None, crops: set[str], tags: set[str]) -> list[dict]:
        """Items for one producer (#15 spec). Location, crops and tags come from conversation state.

        A row qualifies if its tags overlap `tags`, its crop (if any) is one of `crops`, and it is a
        region row for this region, a country row for this country, or a global row. At most 8,
        region rows first. Never substitutes another region.
        """
        cc, key = country_code(country), normalize(admin1)
        picked = {"region": [], "country": [], "global": []}
        for r in self.rows:
            if not set(r["tags"].split(";")) & tags:
                continue
            if r["crop"] and r["crop"] not in crops:
                continue
            if r["scope"] == "region" and not (cc and r["country"] == cc and key and normalize(r["admin1"]) == key):
                continue
            if r["scope"] == "country" and r["country"] != cc:
                continue
            picked[r["scope"]].append(r)
        rows = (picked["region"] + picked["country"] + picked["global"])[:MAX_ITEMS]
        return [{"source": source_label(r), "kind": "regional", "text": fact_text(r), "period": r["period"],
                 "strength": STRENGTH[r["scope"]], "data": dict(r)} for r in rows]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=["fetch", "build"])
    args = parser.parse_args(argv)
    if args.step == "fetch":
        sources = fetch()
        SOURCES_PATH.write_text(json.dumps(sources, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {SOURCES_PATH}", file=sys.stderr)
    else:
        rows = build(json.loads(SOURCES_PATH.read_text(encoding="utf-8")))
        write_csv(rows)
        counts = Counter(r["scope"] for r in rows)
        print(f"wrote {FACTS_PATH}: {len(rows)} facts ({dict(counts)})", file=sys.stderr)


if __name__ == "__main__":
    main()
