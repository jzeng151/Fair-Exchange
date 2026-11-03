"""CHIRPS rainfall connector via the ClimateSERV API.

CHIRPS (Climate Hazards Center InfraRed Precipitation with Station data) is a
quasi-global (50S-50N), ~5 km daily rainfall dataset covering 1981-present.
We reach it through SERVIR's ClimateSERV service, which needs no credentials.

ClimateSERV is an asynchronous, three-step API:
    1. POST/GET submitDataRequest  -> returns a request id
    2. poll getDataRequestProgress -> wait until 100
    3. GET getDataFromRequest      -> returns the time series

Reference for the request shape:
    https://github.com/SERVIR/ClimateSERV  (datatype=0 is CHIRPS rainfall)
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import List, Optional

import requests

from .models import DateRange, Location, RainfallSeries

# ClimateSERV datatype id for CHIRPS daily rainfall.
_CHIRPS_DATATYPE = 0

# operationtype 5 == "download" (raw values) in the ClimateSERV vocabulary.
# For a small bbox this returns the average value per time step, which for a
# point-sized box is effectively the point value.
_OPERATION_DOWNLOAD = 5

# ClimateSERV interval type: 0 == daily.
_INTERVAL_DAILY = 0


class ClimateServError(RuntimeError):
    """Raised when the ClimateSERV API returns an error or times out."""


class CHIRPSClient:
    """Fetch daily CHIRPS rainfall for a point location.

    Example:
        client = CHIRPSClient()
        series = client.get_rainfall(
            Location(lat=-1.95, lon=30.06, name="Kigali"),
            DateRange.parse("2023-01-01", "2023-03-31"),
        )
        print(series.total_mm())
    """

    DEFAULT_BASE_URL = "https://climateserv.servirglobal.net"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        poll_interval: float = 2.0,
        max_poll_seconds: float = 180.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_poll_seconds = max_poll_seconds
        self._session = session or requests.Session()

    # -- public API ---------------------------------------------------------

    def get_rainfall(self, location: Location, when: DateRange) -> RainfallSeries:
        """Return a daily rainfall series (mm/day) for the location."""
        request_id = self._submit(location, when)
        self._wait_until_ready(request_id)
        raw = self._fetch(request_id)
        return self._parse(location, raw)

    # -- step 1: submit -----------------------------------------------------

    def _submit(self, location: Location, when: DateRange) -> str:
        geometry = location.bbox(pad=0.05).as_geojson_polygon()
        params = {
            "datatype": _CHIRPS_DATATYPE,
            "begintime": _fmt(when.start),
            "endtime": _fmt(when.end),
            "intervaltype": _INTERVAL_DAILY,
            "operationtype": _OPERATION_DOWNLOAD,
            "dateType_Category": "default",
            "isZip_CurrentDataType": "false",
            # ClimateSERV expects the geometry as a JSON string in the query.
            "geometry": requests.compat.json.dumps(geometry),
        }
        url = f"{self.base_url}/chirps/submitDataRequest/"
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        # The API returns the request id as a JSON-quoted string, e.g. "abc123".
        request_id = resp.json()
        if isinstance(request_id, list) and request_id:
            request_id = request_id[0]
        if not request_id:
            raise ClimateServError("submitDataRequest returned no request id")
        return str(request_id)

    # -- step 2: poll -------------------------------------------------------

    def _wait_until_ready(self, request_id: str) -> None:
        url = f"{self.base_url}/chirps/getDataRequestProgress/"
        deadline = time.monotonic() + self.max_poll_seconds
        while True:
            resp = self._session.get(
                url, params={"id": request_id}, timeout=self.timeout
            )
            resp.raise_for_status()
            progress = resp.json()
            # Progress comes back as a number or a single-element list.
            if isinstance(progress, list):
                progress = progress[0] if progress else 0
            try:
                pct = float(progress)
            except (TypeError, ValueError):
                pct = 0.0
            if pct >= 100.0:
                return
            if time.monotonic() > deadline:
                raise ClimateServError(
                    f"CHIRPS request {request_id} not ready after "
                    f"{self.max_poll_seconds:.0f}s (last progress {pct})"
                )
            time.sleep(self.poll_interval)

    # -- step 3: fetch ------------------------------------------------------

    def _fetch(self, request_id: str) -> dict:
        url = f"{self.base_url}/chirps/getDataFromRequest/"
        resp = self._session.get(
            url, params={"id": request_id}, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    # -- parsing ------------------------------------------------------------

    @staticmethod
    def _parse(location: Location, raw: dict) -> RainfallSeries:
        """Turn the ClimateSERV response into a RainfallSeries.

        The response shape is roughly:
            {"data": [{"date": "01/15/2023", "value": {"avg": 3.2}}, ...]}
        Dates come back as MM/DD/YYYY; values are nested under "value".
        """
        series = RainfallSeries(location=location, source="CHIRPS")
        points = raw.get("data", []) if isinstance(raw, dict) else []
        for point in points:
            raw_date = point.get("date")
            parsed_date = _parse_cs_date(raw_date)
            value = point.get("value")
            if isinstance(value, dict):
                # Prefer the average; fall back to the first numeric field.
                value = value.get("avg", next(iter(value.values()), None))
            series.dates.append(parsed_date)
            series.values_mm.append(_as_float(value))
        return series


# -- small helpers ----------------------------------------------------------


def _fmt(d: date) -> str:
    """ClimateSERV wants dates as MM/DD/YYYY."""
    return d.strftime("%m/%d/%Y")


def _parse_cs_date(value: object) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def _as_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # ClimateSERV uses large negative sentinels for no-data.
    if f <= -9000:
        return None
    return f
