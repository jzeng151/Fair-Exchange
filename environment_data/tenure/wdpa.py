"""WDPA connector — protected areas (Protected Planet / UNEP-WCMC).

The World Database on Protected Areas is the global reference for terrestrial and
marine protected areas. For stewardship claims, the useful question is whether a
producer location sits in or near a protected area (which affects what land-use
claims are credible and what oversight applies).

Access requires a FREE Personal API Token from Protected Planet:
    request one at  https://api.protectedplanet.net/request
    then set it as the WDPA_TOKEN environment variable (or pass token=...).

IMPORTANT — verification status:
    Unlike the other connectors in this project, this one could not be live-tested
    here because it needs your token. It is built against the documented v3 API
    (https://api.protectedplanet.net). The token is passed as the `token` query
    param. The search endpoint supports a bounding-box / geometry filter; we use a
    small bbox around the point as the practical "near this location" query, then
    report the protected areas found. Once you add a token, run:
        python -m tools.smoke wdpa --lat ... --lon ...
    and confirm the response shape matches _parse() below; adjust field names if
    Protected Planet has changed them.
"""

from __future__ import annotations

import os
from typing import List, Optional

import requests

from common.geo import Location
from common.results import PointObservation, PointResult


class WDPAConfigError(RuntimeError):
    """Raised when the WDPA token is missing."""


class WDPAError(RuntimeError):
    """Raised when the Protected Planet API errors."""


class WDPAClient:
    """Find protected areas at/near a location via Protected Planet.

    Example:
        client = WDPAClient()  # reads WDPA_TOKEN from the environment
        result = client.get_protected_areas(Location(-2.0, 34.8, "Serengeti"))
        pa = result.get("in_protected_area")
        print(pa.value, pa.detail["areas"])
    """

    DEFAULT_BASE_URL = "https://api.protectedplanet.net/v3"

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 45.0,
        search_radius_deg: float = 0.1,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.token = token or os.getenv("WDPA_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.search_radius_deg = search_radius_deg
        self._session = session or requests.Session()

    def get_protected_areas(self, location: Location) -> PointResult:
        """Return protected areas found in a small bbox around the location."""
        if not self.token:
            raise WDPAConfigError(
                "No WDPA token. Request a free token at "
                "https://api.protectedplanet.net/request and set WDPA_TOKEN "
                "(or pass token=...)."
            )

        box = location.bbox(pad=self.search_radius_deg)
        # Protected Planet search accepts a bounding box as a comma list
        # [west, south, east, north].
        params = {
            "token": self.token,
            "with_geometry": "false",
            "per_page": 50,
            "bbox": f"{box.min_lon},{box.min_lat},{box.max_lon},{box.max_lat}",
        }
        url = f"{self.base_url}/protected_areas/search"
        resp = self._session.get(url, params=params, timeout=self.timeout)
        if resp.status_code == 401:
            raise WDPAConfigError(
                "WDPA token rejected (HTTP 401). Check WDPA_TOKEN is valid."
            )
        if resp.status_code != 200:
            raise WDPAError(
                f"Protected Planet returned HTTP {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        return self._parse(location, resp.json())

    @staticmethod
    def _parse(location: Location, payload: dict) -> PointResult:
        result = PointResult(location=location, source="WDPA")
        areas_raw = payload.get("protected_areas", []) if isinstance(payload, dict) else []
        areas: List[dict] = []
        for pa in areas_raw:
            areas.append(
                {
                    "wdpa_id": pa.get("wdpa_id") or pa.get("id"),
                    "name": pa.get("name"),
                    "designation": (pa.get("designation") or {}).get("name")
                    if isinstance(pa.get("designation"), dict)
                    else pa.get("designation"),
                    "iucn_category": (pa.get("iucn_category") or {}).get("name")
                    if isinstance(pa.get("iucn_category"), dict)
                    else pa.get("iucn_category"),
                    "marine": pa.get("marine"),
                }
            )
        result.observations.append(
            PointObservation(
                name="in_protected_area",
                value=bool(areas),
                unit="boolean",
                detail={"n_areas": len(areas), "areas": areas},
            )
        )
        return result
