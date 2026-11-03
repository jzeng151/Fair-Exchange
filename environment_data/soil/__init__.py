"""Soil and land data connectors.

    SoilGridsClient  -- soil carbon, pH, nitrogen, etc. (ISRIC, no auth)
    JRCForestClient  -- tropical moist forest cover/loss (JRC)
"""

from .soilgrids import SoilGridsClient
from .jrc_forest import JRCForestClient

__all__ = ["SoilGridsClient", "JRCForestClient"]
