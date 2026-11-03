"""Biodiversity and land-tenure connectors.

    LandMarkClient  -- Indigenous & community lands (WRI LandMark, no auth)
    WDPAClient      -- protected areas (Protected Planet, free token)
"""

from .landmark import LandMarkClient
from .wdpa import WDPAClient

__all__ = ["LandMarkClient", "WDPAClient"]
