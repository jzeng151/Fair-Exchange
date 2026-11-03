# Fair Trade USA Producer Exchange Agent — Environmental Data Connectors

Data access layer for the Producer Exchange Agent MVP. Each connector takes a
producer `Location` (lat/lon) and returns a normalized result the agent can use
to support sustainability / stewardship claims.

## Sources and status

| Category | Source | What it gives | Auth | Live-tested |
| -------- | ------ | ------------- | ---- | ----------- |
| Climate | **CHIRPS** | daily rainfall (mm) | none | ✅ yes |
| Climate | **ERA5** | temp / precip reanalysis | free CDS key | request builds; needs key to run |
| Soil & land | **SoilGrids** | soil carbon, pH, N, CEC, clay… | none | ✅ yes |
| Soil & land | **JRC TMF** | tropical forest class + deforestation year | Earth Engine acct | built vs. docs; needs EE to run |
| Water | **Aqueduct** | baseline + projected (2030/50/80) water stress | none | ✅ yes |
| Biodiversity / tenure | **LandMark** | is point on Indigenous / community land? | none | ✅ yes |
| Biodiversity / tenure | **WDPA** | protected areas near a point | free token | built vs. docs; needs token to run |

Four sources (CHIRPS, SoilGrids, Aqueduct, LandMark) work with **no credentials**
and are verified end-to-end. The other three need a free account/key, documented
below; their code is written against the published APIs and clearly flags that it
needs your credential to be fully exercised.

## Layout

```
common/        shared models: Location, BBox, DateRange, PointResult, PointObservation
climate/       CHIRPS (chirps.py), ERA5 (era5.py)  -> time series
soil/          SoilGrids (soilgrids.py), JRC TMF (jrc_forest.py)
water/         Aqueduct (aqueduct.py)
tenure/        LandMark (landmark.py), WDPA (wdpa.py)
tools/smoke.py one CLI to test any source
config/.env.example
```

Two result shapes:
- **Time series** (climate): `RainfallSeries`, `ClimateSeries` — a value per day.
- **Point result** (soil/water/tenure): `PointResult` holding named
  `PointObservation`s (value + unit + detail) — answers a question about a place.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# No-auth sources — work immediately:
python -m tools.smoke soilgrids --lat 52.0   --lon 5.1
python -m tools.smoke aqueduct  --lat -1.3   --lon 36.8
python -m tools.smoke landmark  --lat -16.92 --lon -39.27
python -m tools.smoke chirps    --lat -1.95  --lon 30.06 --start 2023-01-01 --end 2023-03-31
```

## Use from Python

```python
from common import Location, DateRange
from soil import SoilGridsClient
from water import AqueductClient
from tenure import LandMarkClient
from climate import CHIRPSClient

loc = Location(-1.3, 36.8, "Nairobi")

soil  = SoilGridsClient().get_soil(loc)
water = AqueductClient().get_water_risk(loc)
land  = LandMarkClient().get_land_tenure(loc)
rain  = CHIRPSClient().get_rainfall(loc, DateRange.parse("2023-01-01", "2023-03-31"))

print(soil.get("soil_organic_carbon").value)       # g/kg
print(water.get("water_stress_bau_2050").value)    # projected category
print(land.get("indigenous_or_community_land").value)  # True/False
print(rain.total_mm())
```

Every point source returns `result.to_dict()` as clean JSON for the agent layer.

## Credentials — what you need to do

CHIRPS, SoilGrids, Aqueduct, LandMark: **nothing.** The three below are free but
require a one-time signup.

### ERA5 (Copernicus CDS)
1. Create a free account: https://cds.climate.copernicus.eu
2. Accept the ERA5 licence on the dataset page (one-time).
3. Copy your API key from your CDS profile.
4. `cp config/.env.example config/.env` and paste the key into `CDSAPI_KEY`.
5. Test: `python -m tools.smoke era5 --lat -1.95 --lon 30.06 --start 2023-01-01 --end 2023-01-31`

### WDPA (Protected Planet)
1. Request a free Personal API Token: https://api.protectedplanet.net/request
2. `export WDPA_TOKEN=your-token` (or add it to `config/.env`).
3. Test: `python -m tools.smoke wdpa --lat -2.33 --lon 34.83`
4. On first real response, confirm the field names in `tenure/wdpa.py::_parse`
   still match Protected Planet's output (they occasionally rename fields).

### JRC TMF (Google Earth Engine)
1. Sign up for Earth Engine: https://earthengine.google.com (free, needs a
   Google Cloud project).
2. `pip install earthengine-api`
3. `earthengine authenticate` (one-time browser login).
4. `export EE_PROJECT=your-gcp-project-id`
5. Test: `python -m tools.smoke jrc --lat -3.5 --lon -62.5`
   (A no-auth WMS fallback exists but is only demo-grade; see notes in
   `soil/jrc_forest.py`.)
