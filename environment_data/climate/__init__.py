"""Climate data connectors for the FTUSA Producer Exchange Agent.

Public surface:
    Location, DateRange, RainfallSeries, ClimateSeries  -- data models
    CHIRPSClient                                         -- rainfall (no auth)
    ERA5Client                                           -- temp/precip reanalysis (CDS key)
"""

from .models import ClimateSeries, DateRange, Location, RainfallSeries
from .chirps import CHIRPSClient
from .era5 import ERA5Client

__all__ = [
    "Location",
    "DateRange",
    "RainfallSeries",
    "ClimateSeries",
    "CHIRPSClient",
    "ERA5Client",
]
