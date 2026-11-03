"""LandMark connector — Indigenous and community lands.

LandMark (hosted by WRI) maps lands collectively held/used by Indigenous Peoples
and local communities. For stewardship claims and FPIC-related context, the
useful question is: does this producer location fall within mapped Indigenous or
community land, and what is its legal/documentation status?

Served anonymously from WRI's ArcGIS server (no credentials):
    https://gis.wri.org/server/rest/services/LandMark/<service>/MapServer

Each service has a point sublayer (0) and a polygon sublayer (1); we query the
polygon layer with a point-in-polygon spatial query. We check both Indigenous
(comm_ind_*) and community (comm_comm_*) lands across documentation statuses.

Coverage is incomplete by design (the LandMark team notes ongoing gaps), so "no
match" means "not in LandMark's mapped data", NOT "definitely not community land".
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import requests

from common.geo import Location
from common.results import PointObservation, PointResult

_BASE = "https://gis.wri.org/server/rest/services/LandMark"
_POLYGON_LAYER = 1  # sublayer 1 is the polygon geometry

# service name -> (identity, documentation status) for the lands we check.
_SERVICES = {
    "comm_ind_Documented": ("Indigenous", "Documented"),
    "comm_ind_CustomaryTenure": ("Indigenous", "Held under customary tenure"),
    "comm_ind_FormalLandClaim": ("Indigenous", "Formal land claim"),
    "comm_comm_Documented": ("Community", "Documented"),
    "comm_comm_CustomaryTenure": ("Community", "Held under customary tenure"),
    "comm_comm_FormalLandClaim": ("Community", "Formal land claim"),
}


class LandMarkError(RuntimeError):
    """Raised when the LandMark service errors."""


class LandMarkClient:
    """Check whether a location falls within mapped Indigenous/community land.

    Example:
        client = LandMarkClient()
        result = client.get_land_tenure(Location(-16.92, -39.27))
        hit = result.get("indigenous_or_community_land")
        print(hit.value)        # True / False
        print(hit.detail)       # matched land name, category, status
    """

    def __init__(
        self,
        base_url: str = _BASE,
        timeout: float = 45.0,
        services: Optional[Dict[str, tuple]] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.services = services or _SERVICES
        self._session = session or requests.Session()

    def get_land_tenure(self, location: Location) -> PointResult:
        """Return whether the point intersects mapped Indigenous/community land."""
        result = PointResult(location=location, source="LandMark")
        matches: List[dict] = []

        for service, (identity, status) in self.services.items():
            feature = self._query_point(service, location)
            if feature is not None:
                matches.append(
                    {
                        "identity": identity,
                        "status": status,
                        "name": feature.get("Name"),
                        "category": feature.get("Category"),
                        "country": feature.get("Country"),
                    }
                )

        result.observations.append(
            PointObservation(
                name="indigenous_or_community_land",
                value=bool(matches),
                unit="boolean",
                detail={"matches": matches, "n_matches": len(matches)},
            )
        )
        return result

    # -- internals ----------------------------------------------------------

    def _query_point(self, service: str, location: Location) -> Optional[dict]:
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
            "outFields": "Name,Category,Country,Identity",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 1,
        }
        url = f"{self.base_url}/{service}/MapServer/{_POLYGON_LAYER}/query"
        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise LandMarkError(f"LandMark query failed for {service}: {exc}") from exc
        if "error" in payload:
            raise LandMarkError(f"LandMark API error on {service}: {payload['error']}")
        features = payload.get("features") or []
        return features[0].get("attributes") if features else None
