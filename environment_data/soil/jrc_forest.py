"""JRC Tropical Moist Forest (TMF) connector.

JRC TMF is a 30 m wall-to-wall map of tropical moist forest extent and its
disturbances (deforestation, degradation, regrowth) over 1990-2025. It flags
forest cover and loss, which matters for erosion/degradation risk and for
agroforestry / soil-health claims.

ACCESS REALITY (important):
    TMF has no simple anonymous point API. The two real options are:

    (A) Google Earth Engine  [implemented here, AUTHORITATIVE]
        Exact pixel class codes from the published TMF assets. Requires a free
        Earth Engine account + authentication (like WDPA's token, this is a
        credential this project could not exercise during the build, so the GEE
        path is built against the documented asset/band names and marked for you
        to verify once authenticated).

    (B) JRC WMS GetMap color sampling  [see note below, NO AUTH, approximate]
        The public TMF WMS (ies-ows.jrc.ec.europa.eu) renders map tiles but its
        GetFeatureInfo is unreliable (returns 500) and 1x1 GetMap sampling at
        high zoom returns empty/transparent pixels. So color-sampling is only a
        rough demo-grade fallback, not a dependable source. It is intentionally
        NOT the default here.

Setup for the GEE path:
    pip install earthengine-api
    earthengine authenticate        # one-time, opens a browser
    # then set your Cloud project:
    export EE_PROJECT=your-gcp-project-id

TMF transition/annual-change class codes are documented in the TMF Data Users
Guide (https://forobs.jrc.ec.europa.eu/static/tmf/TMF_DataUsersGuide.pdf).
"""

from __future__ import annotations

import os
from typing import Optional

from common.geo import Location
from common.results import PointObservation, PointResult

# TMF "TransitionMap_MainClasses" top-level classes (from the Data Users Guide).
# Used to translate the raw integer the GEE asset returns into a label.
_TMF_MAIN_CLASS = {
    10: "Undisturbed tropical moist forest",
    20: "Degraded tropical moist forest",
    30: "Deforested land",
    40: "Tropical moist forest regrowth",
    50: "Permanent or seasonal water",
    60: "Other land cover",
}


class JRCForestError(RuntimeError):
    """Raised when the TMF/GEE lookup fails or is not configured."""


class JRCForestClient:
    """Fetch JRC TMF forest state at a point via Google Earth Engine.

    Example (after `earthengine authenticate` and EE_PROJECT set):
        client = JRCForestClient()
        result = client.get_forest(Location(-3.5, -62.5, "Amazon"))
        print(result.get("tmf_main_class").value)
    """

    # Published TMF asset collection on Earth Engine.
    TRANSITION_ASSET = "projects/JRC/TMF/v1_2023/TransitionMap_MainClasses"
    DEFORESTATION_ASSET = "projects/JRC/TMF/v1_2023/DeforestationYear"

    def __init__(self, ee_project: Optional[str] = None) -> None:
        self.ee_project = ee_project or os.getenv("EE_PROJECT")
        self._ee = None  # lazily initialised

    def get_forest(self, location: Location) -> PointResult:
        """Return TMF main class + deforestation year at the location."""
        ee = self._ensure_ee()
        point = ee.Geometry.Point([location.lon, location.lat])

        result = PointResult(location=location, source="JRC-TMF")

        main_class = self._sample(ee, self.TRANSITION_ASSET, point)
        result.observations.append(
            PointObservation(
                name="tmf_main_class",
                value=_TMF_MAIN_CLASS.get(main_class, main_class),
                unit="class",
                detail={"class_code": main_class, "asset": self.TRANSITION_ASSET},
            )
        )

        defor_year = self._sample(ee, self.DEFORESTATION_ASSET, point)
        result.observations.append(
            PointObservation(
                name="deforestation_year",
                # 0 / None means no deforestation detected at that pixel.
                value=defor_year if defor_year else None,
                unit="year",
                detail={"asset": self.DEFORESTATION_ASSET},
            )
        )
        return result

    # -- internals ----------------------------------------------------------

    def _ensure_ee(self):
        if self._ee is not None:
            return self._ee
        try:
            import ee  # type: ignore
        except ImportError as exc:
            raise JRCForestError(
                "earthengine-api is not installed. Run: pip install earthengine-api"
            ) from exc
        try:
            if self.ee_project:
                ee.Initialize(project=self.ee_project)
            else:
                ee.Initialize()
        except Exception as exc:  # noqa: BLE001
            raise JRCForestError(
                "Earth Engine is not authenticated/initialised. Run "
                "`earthengine authenticate` and set EE_PROJECT to your Cloud "
                f"project id. Underlying error: {exc}"
            ) from exc
        self._ee = ee
        return ee

    def _sample(self, ee, asset_id: str, point) -> Optional[int]:
        """Sample a single-band image at a point, returning the integer value."""
        try:
            image = ee.Image(asset_id)
            sample = image.reduceRegion(
                reducer=ee.Reducer.first(), geometry=point, scale=30
            )
            info = sample.getInfo() or {}
        except Exception as exc:  # noqa: BLE001
            raise JRCForestError(f"TMF sample failed for {asset_id}: {exc}") from exc
        if not info:
            return None
        # The single band's value (band name varies by asset).
        value = next(iter(info.values()), None)
        return int(value) if value is not None else None
