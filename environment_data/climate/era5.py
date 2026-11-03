"""ERA5 reanalysis connector via the Copernicus Climate Data Store (CDS).

ERA5 is ECMWF's global reanalysis (1940-present, hourly, ~31 km). We pull two
variables relevant to producer regions:
    - 2m_temperature        (near-surface air temperature, Kelvin)
    - total_precipitation   (accumulated precipitation, metres)

Access requires a free CDS account. The `cdsapi` client reads credentials from
~/.cdsapirc or from the CDSAPI_URL / CDSAPI_KEY environment variables. This
module supports both and also lets you pass them explicitly.

Register and get a key: https://cds.climate.copernicus.eu
"""

from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from typing import List, Optional

from .models import ClimateSeries, DateRange, Location

# CDS dataset id for hourly ERA5 single-level fields.
_ERA5_DATASET = "reanalysis-era5-single-levels"

_VARIABLE_UNITS = {
    "2m_temperature": "K",
    "total_precipitation": "m",
}


class ERA5ConfigError(RuntimeError):
    """Raised when CDS credentials are missing or invalid."""


class ERA5Client:
    """Fetch ERA5 reanalysis series for a point location.

    Lazily imports cdsapi/xarray so that importing this module (and the CHIRPS
    client alongside it) does not require the heavier scientific stack.

    Example:
        client = ERA5Client()  # reads ~/.cdsapirc or env vars
        series = client.get_series(
            Location(-1.95, 30.06, "Kigali"),
            DateRange.parse("2023-01-01", "2023-01-31"),
            variable="2m_temperature",
        )
    """

    def __init__(
        self,
        cds_url: Optional[str] = None,
        cds_key: Optional[str] = None,
    ) -> None:
        self.cds_url = cds_url or os.getenv("CDSAPI_URL")
        self.cds_key = cds_key or os.getenv("CDSAPI_KEY")

    # -- public API ---------------------------------------------------------

    def get_series(
        self,
        location: Location,
        when: DateRange,
        variable: str = "2m_temperature",
    ) -> ClimateSeries:
        """Download a daily-aggregated ERA5 series for one variable.

        Hourly data is averaged (temperature) or summed (precipitation) to a
        daily value, which is the useful granularity for trend statements.
        """
        if variable not in _VARIABLE_UNITS:
            raise ValueError(
                f"unsupported variable {variable!r}; "
                f"choose from {sorted(_VARIABLE_UNITS)}"
            )

        client = self._build_client()
        xr = _import_xarray()

        request = self._build_request(location, when, variable)
        with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
            target = tmp.name
        try:
            client.retrieve(_ERA5_DATASET, request, target)
            ds = xr.open_dataset(target)
            try:
                return self._aggregate(ds, location, variable)
            finally:
                ds.close()
        finally:
            if os.path.exists(target):
                os.remove(target)

    # -- internals ----------------------------------------------------------

    def _build_client(self):
        cdsapi = _import_cdsapi()
        kwargs = {}
        if self.cds_url and self.cds_key:
            kwargs = {"url": self.cds_url, "key": self.cds_key}
        try:
            # With no kwargs, cdsapi falls back to ~/.cdsapirc.
            return cdsapi.Client(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface a clear message
            raise ERA5ConfigError(
                "Could not initialise the CDS client. Set CDSAPI_URL and "
                "CDSAPI_KEY (see config/.env.example) or create ~/.cdsapirc. "
                f"Underlying error: {exc}"
            ) from exc

    @staticmethod
    def _build_request(
        location: Location, when: DateRange, variable: str
    ) -> dict:
        days = _days_between(when.start, when.end)
        years = sorted({str(d.year) for d in days})
        months = sorted({f"{d.month:02d}" for d in days})
        day_nums = sorted({f"{d.day:02d}" for d in days})
        # Tight area around the point: [North, West, South, East].
        box = location.bbox(pad=0.25)
        return {
            "product_type": "reanalysis",
            "variable": variable,
            "year": years,
            "month": months,
            "day": day_nums,
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": [box.max_lat, box.min_lon, box.min_lat, box.max_lon],
            "format": "netcdf",
        }

    @staticmethod
    def _aggregate(ds, location: Location, variable: str) -> ClimateSeries:
        """Collapse the lat/lon box to a point and hourly data to daily."""
        # ERA5 NetCDF names: t2m for temperature, tp for total precipitation.
        var_name = {"2m_temperature": "t2m", "total_precipitation": "tp"}[
            variable
        ]
        data = ds[var_name]

        # Spatial mean over the small box -> a single column over time.
        spatial_dims = [d for d in ("latitude", "longitude") if d in data.dims]
        if spatial_dims:
            data = data.mean(dim=spatial_dims)

        # Resample hourly -> daily. Precip accumulates (sum); temp averages.
        time_dim = "time" if "time" in data.dims else data.dims[0]
        if variable == "total_precipitation":
            daily = data.resample({time_dim: "1D"}).sum()
        else:
            daily = data.resample({time_dim: "1D"}).mean()

        series = ClimateSeries(
            location=location,
            source="ERA5",
            variable=variable,
            unit=_VARIABLE_UNITS[variable],
        )
        times = daily[time_dim].values
        values = daily.values
        for t, v in zip(times, values):
            series.dates.append(_np_datetime_to_date(t))
            series.values.append(None if _is_nan(v) else float(v))
        return series


# -- lazy imports so the base install stays light ---------------------------


def _import_cdsapi():
    try:
        import cdsapi  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ERA5ConfigError(
            "cdsapi is not installed. Run: pip install cdsapi"
        ) from exc
    return cdsapi


def _import_xarray():
    try:
        import xarray  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ERA5ConfigError(
            "xarray + netCDF4 are needed to read ERA5. "
            "Run: pip install xarray netCDF4"
        ) from exc
    return xarray


# -- small helpers ----------------------------------------------------------


def _days_between(start: date, end: date) -> List[date]:
    out, current = [], start
    while current <= end:
        out.append(current)
        current += timedelta(days=1)
    return out


def _np_datetime_to_date(value) -> date:
    # numpy.datetime64 -> python date
    import numpy as np  # local import; numpy ships with xarray

    ts = (value - np.datetime64("1970-01-01T00:00:00")) / np.timedelta64(1, "s")
    from datetime import datetime, timezone

    return datetime.fromtimestamp(float(ts), tz=timezone.utc).date()


def _is_nan(value) -> bool:
    try:
        return value != value  # NaN is the only value not equal to itself
    except Exception:  # noqa: BLE001
        return False
