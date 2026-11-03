"""Aqueduct Water Risk Atlas connector (WRI Aqueduct 4.0).

Aqueduct 4.0 translates hydrological model output into water-risk indicators per
HydroBASINS level-6 sub-basin, with BOTH current ("baseline") conditions and
future projections for 2030/2050/2080 under three scenarios. That future view is
what lets the agent make forward-looking water-stress statements rather than
describing only current conditions.

Data is reached through WRI's public ArcGIS feature service (no credentials):
    https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/aqueduct_water_risk/FeatureServer
        layer 1 = Baseline Annual   (bws_* = baseline water stress)
        layer 0 = Future Annual     ({scenario}{year}_ws_x_{r|s|c|l})

Future field naming:
    scenario: bau (business-as-usual), opt (optimistic), pes (pessimistic)
    year:     30 (2030), 50 (2050), 80 (2080)
    suffix:   _r raw, _s score, _c category, _l label
    e.g. bau50_ws_x_l = BAU 2050 water-stress label.
"""

from __future__ import annotations

import json
from typing import List, Optional

import requests

from common.geo import Location
from common.results import PointObservation, PointResult

_BASE = (
    "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/"
    "aqueduct_water_risk/FeatureServer"
)
_BASELINE_LAYER = 1
_FUTURE_LAYER = 0

_SCENARIOS = {"bau": "business_as_usual", "opt": "optimistic", "pes": "pessimistic"}
_YEARS = {"30": 2030, "50": 2050, "80": 2080}


class AqueductError(RuntimeError):
    """Raised when the Aqueduct feature service errors or returns nothing."""


class AqueductClient:
    """Query baseline and projected water stress for a point location.

    Example:
        client = AqueductClient()
        result = client.get_water_risk(Location(-1.3, 36.8, "Nairobi"))
        print(result.get("baseline_water_stress").value)
        print(result.get("water_stress_bau_2050").value)
    """

    def __init__(
        self,
        base_url: str = _BASE,
        timeout: float = 45.0,
        scenario: str = "bau",
        session: Optional[requests.Session] = None,
    ) -> None:
        if scenario not in _SCENARIOS:
            raise ValueError(
                f"scenario must be one of {sorted(_SCENARIOS)}, got {scenario!r}"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.scenario = scenario
        self._session = session or requests.Session()

    def get_water_risk(self, location: Location) -> PointResult:
        """Return baseline + projected water-stress for the location."""
        result = PointResult(location=location, source="Aqueduct")

        baseline = self._query_point(
            layer=_BASELINE_LAYER,
            location=location,
            out_fields="name_0,name_1,bws_label,bws_score,bws_cat",
        )
        if baseline:
            result.observations.append(
                PointObservation(
                    name="baseline_water_stress",
                    value=baseline.get("bws_label"),
                    unit="category",
                    detail={
                        "score": baseline.get("bws_score"),
                        "category_code": baseline.get("bws_cat"),
                        "admin0": baseline.get("name_0"),
                        "admin1": baseline.get("name_1"),
                    },
                )
            )

        # Projected water stress for each milestone year under the scenario.
        future_fields = [f"{self.scenario}{y}_ws_x_l" for y in _YEARS]
        future_scores = [f"{self.scenario}{y}_ws_x_s" for y in _YEARS]
        future = self._query_point(
            layer=_FUTURE_LAYER,
            location=location,
            out_fields=",".join(future_fields + future_scores),
        )
        if future:
            for code, year in _YEARS.items():
                label = future.get(f"{self.scenario}{code}_ws_x_l")
                score = future.get(f"{self.scenario}{code}_ws_x_s")
                result.observations.append(
                    PointObservation(
                        name=f"water_stress_{self.scenario}_{year}",
                        value=label,
                        unit="category",
                        detail={"score": score, "scenario": _SCENARIOS[self.scenario]},
                    )
                )

        if not result.observations:
            raise AqueductError(
                f"No Aqueduct sub-basin found at {location.lat},{location.lon}"
            )
        return result

    # -- internals ----------------------------------------------------------

    def _query_point(
        self, layer: int, location: Location, out_fields: str
    ) -> Optional[dict]:
        geometry = {
            "x": location.lon,
            "y": location.lat,
            "spatialReference": {"wkid": 4326},
        }
        params = {
            "geometry": json.dumps(geometry),
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
        }
        url = f"{self.base_url}/{layer}/query"
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            raise AqueductError(f"Aqueduct API error: {payload['error']}")
        features = payload.get("features") or []
        if not features:
            return None
        return features[0].get("attributes") or {}
