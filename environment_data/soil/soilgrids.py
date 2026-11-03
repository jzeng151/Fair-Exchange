"""SoilGrids connector via the ISRIC REST API.

SoilGrids (ISRIC) is a global, 250 m, machine-learning soil property map. We
read point values that flag soil health and degradation risk for agroforestry
and soil-health projects:

    soc       soil organic carbon       (g/kg)
    phh2o     pH in water               (-)
    nitrogen  total nitrogen            (g/kg)
    cec       cation exchange capacity  (cmol(c)/kg)
    bdod      bulk density              (kg/dm3)
    clay      clay content              (%)

The REST API is open (CC-BY 4.0) and needs no credentials:
    https://rest.isric.org/soilgrids/v2.0/properties/query

API values are stored as integers; each layer carries a `d_factor` so the
conventional unit = raw_value / d_factor. We apply that here.

Note: SoilGrids returns null for some pixels (water, coverage gaps). We surface
those as a None value rather than failing, so callers can degrade gracefully.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import requests

from common.geo import Location
from common.results import PointObservation, PointResult

# Default set of properties worth pulling for soil-health context.
DEFAULT_PROPERTIES = ["soc", "phh2o", "nitrogen", "cec", "bdod", "clay"]

# Human-friendly names + target units (after d_factor conversion).
_PROPERTY_META = {
    "soc": ("soil_organic_carbon", "g/kg"),
    "phh2o": ("ph_h2o", "-"),
    "nitrogen": ("total_nitrogen", "g/kg"),
    "cec": ("cation_exchange_capacity", "cmol(c)/kg"),
    "bdod": ("bulk_density", "kg/dm3"),
    "clay": ("clay_content", "%"),
    "sand": ("sand_content", "%"),
    "silt": ("silt_content", "%"),
    "cfvo": ("coarse_fragments", "cm3/100cm3"),
    "ocd": ("organic_carbon_density", "kg/m3"),
    "ocs": ("organic_carbon_stock", "kg/m2"),
}


class SoilGridsError(RuntimeError):
    """Raised when the SoilGrids API errors."""


class SoilGridsClient:
    """Fetch SoilGrids soil properties at a point.

    Example:
        client = SoilGridsClient()
        result = client.get_soil(Location(52.0, 5.1, "NL"))
        print(result.get("soil_organic_carbon").value)  # g/kg
    """

    DEFAULT_BASE_URL = "https://rest.isric.org/soilgrids/v2.0"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
        retries: int = 2,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self._session = session or requests.Session()

    def get_soil(
        self,
        location: Location,
        properties: Optional[List[str]] = None,
        depth: str = "0-5cm",
    ) -> PointResult:
        """Return soil properties at the location for a single depth.

        `depth` is one of SoilGrids' standard intervals:
        0-5cm, 5-15cm, 15-30cm, 30-60cm, 60-100cm, 100-200cm.
        """
        properties = properties or DEFAULT_PROPERTIES
        params = {
            "lon": location.lon,
            "lat": location.lat,
            "property": properties,
            "depth": depth,
            "value": "mean",
        }
        url = f"{self.base_url}/properties/query"
        # SoilGrids is a free public API that intermittently runs slow; retry
        # transient timeouts/5xx before giving up.
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                continue
            if resp.status_code == 200:
                return self._parse(location, resp.json(), depth)
            if resp.status_code < 500:
                raise SoilGridsError(
                    f"SoilGrids returned HTTP {resp.status_code}: {resp.text[:200]}"
                )
            last_exc = SoilGridsError(f"SoilGrids HTTP {resp.status_code}")
        raise SoilGridsError(
            f"SoilGrids request failed after {self.retries + 1} attempts: {last_exc}"
        )

    @staticmethod
    def _parse(location: Location, payload: dict, depth: str) -> PointResult:
        result = PointResult(location=location, source="SoilGrids")
        layers = (payload.get("properties") or {}).get("layers", [])
        for layer in layers:
            raw_name = layer.get("name")
            friendly, unit = _PROPERTY_META.get(raw_name, (raw_name, None))
            d_factor = (layer.get("unit_measure") or {}).get("d_factor", 1) or 1
            mean = _depth_mean(layer, depth)
            value = None if mean is None else round(mean / d_factor, 3)
            result.observations.append(
                PointObservation(
                    name=friendly,
                    value=value,
                    unit=unit,
                    detail={"soilgrids_property": raw_name, "depth": depth},
                )
            )
        return result


def _depth_mean(layer: dict, depth: str) -> Optional[float]:
    """Pull the mean value for the requested depth label from a layer."""
    for dep in layer.get("depths", []):
        if dep.get("label") == depth:
            values = dep.get("values") or {}
            return values.get("mean")
    # Fall back to the first available depth if the label isn't present.
    depths = layer.get("depths") or []
    if depths:
        return (depths[0].get("values") or {}).get("mean")
    return None
