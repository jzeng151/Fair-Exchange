"""Representative lat/lon centroids for producer regions in the synthetic data.

The synthetic producer records identify location as (country, region) admin-1
names, not coordinates. CHIRPS and Aqueduct are queried by point, so we need a
representative point per region. These are approximate admin-1 centroids,
adequate for regional rainfall / water-stress context (both datasets are
sub-basin / ~5 km gridded, so exact farm coordinates are not needed).

Coverage focuses on the agricultural producing regions in the dataset (coffee,
cocoa, produce, bananas, tea). Non-agricultural rows (apparel, home goods) are
intentionally omitted — there is no meaningful climate story for them.

Keys are (country_lower, region_lower). Extend this table to add regions.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# (country, region) -> (lat, lon)
_CENTROIDS: Dict[Tuple[str, str], Tuple[float, float]] = {
    # --- Colombia (coffee, cocoa, bananas, produce) ---
    ("colombia", "antioquia"): (6.55, -75.83),
    ("colombia", "caldas"): (5.30, -75.27),
    ("colombia", "cauca"): (2.44, -76.61),
    ("colombia", "cesar"): (9.34, -73.65),
    ("colombia", "huila"): (2.54, -75.53),
    ("colombia", "norte de santander"): (7.95, -72.90),
    ("colombia", "risaralda"): (5.31, -75.99),
    ("colombia", "tolima"): (4.09, -75.15),
    ("colombia", "valle del cauca"): (3.80, -76.52),
    # --- Peru (coffee, cocoa, produce) ---
    ("peru", "amazonas"): (-5.08, -78.00),
    ("peru", "ancash"): (-9.53, -77.53),
    ("peru", "cajamarca"): (-7.16, -78.51),
    ("peru", "junin"): (-11.54, -74.95),
    ("peru", "lambayeque"): (-6.37, -79.84),
    ("peru", "pasco"): (-10.36, -75.35),
    ("peru", "san martin"): (-6.48, -76.37),
    # --- Honduras (coffee) ---
    ("honduras", "copan"): (14.85, -88.90),
    ("honduras", "intibuca"): (14.32, -88.17),
    ("honduras", "la paz"): (14.32, -87.68),
    ("honduras", "lempira"): (14.59, -88.57),
    ("honduras", "ocotepeque"): (14.43, -89.18),
    # --- Mexico (coffee, produce, seafood) ---
    ("mexico", "chiapas"): (16.75, -92.63),
    ("mexico", "guanajuato"): (21.02, -101.26),
    ("mexico", "michoacan de ocampo"): (19.57, -101.71),
    ("mexico", "sonora"): (29.30, -110.33),
    ("mexico", "sinaloa"): (24.80, -107.40),
    # --- Brazil (coffee) ---
    ("brazil", "amazonas"): (-3.42, -65.86),
    ("brazil", "minas gerais"): (-18.51, -44.56),
    ("brazil", "sao paulo"): (-22.30, -48.60),
    ("brazil", "piaui"): (-7.72, -42.73),
    # --- Ecuador (bananas, produce, flowers) ---
    ("ecuador", "el oro"): (-3.42, -79.80),
    ("ecuador", "cotopaxi"): (-0.84, -78.66),
    # --- Nicaragua (coffee, produce) ---
    ("nicaragua", "boaco"): (12.47, -85.66),
    ("nicaragua", "jinotega"): (13.09, -86.00),
    ("nicaragua", "madriz"): (13.47, -86.46),
    ("nicaragua", "masaya"): (11.97, -86.09),
    # --- Guatemala (coffee, produce) ---
    ("guatemala", "guatemala"): (14.63, -90.51),
    ("guatemala", "huehuetenango"): (15.32, -91.47),
    ("guatemala", "jalapa"): (14.63, -89.99),
    ("guatemala", "quiche"): (15.03, -91.15),
    ("guatemala", "solola"): (14.77, -91.18),
    # --- Côte d'Ivoire (cocoa) ---
    ("côte d’ivoire", "bas-sassandra"): (5.47, -6.62),
    ("côte d’ivoire", "goh-djiboua"): (5.88, -5.57),
    ("côte d’ivoire", "zanzan"): (8.60, -3.20),
    # --- Costa Rica (coffee, pineapple) ---
    ("costa rica", "alajuela"): (10.39, -84.42),
    ("costa rica", "san jose"): (9.83, -84.07),
    # --- Ethiopia / Kenya / Rwanda (coffee, tea) ---
    ("ethiopia", "yedebub biheroch bihereseboch na hizboch"): (6.50, 37.00),
    ("kenya", "kericho"): (-0.37, 35.29),
    ("rwanda", "nord"): (-1.50, 29.75),
    ("rwanda", "ville de kigali"): (-1.95, 30.06),
    # --- India / Indonesia / Sri Lanka (tea, coffee, produce) ---
    ("india", "assam"): (26.20, 92.94),
    ("india", "kerala"): (10.85, 76.27),
    ("india", "tamil nadu"): (11.13, 78.66),
    ("indonesia", "aceh"): (4.70, 96.75),
    ("indonesia", "bali"): (-8.34, 115.09),
    ("sri lanka", "central province"): (7.29, 80.64),
}


def centroid_for(country: str, region: Optional[str]) -> Optional[Tuple[float, float]]:
    """Return (lat, lon) for a (country, region), or None if not catalogued."""
    if not region:
        return None
    return _CENTROIDS.get((country.strip().lower(), region.strip().lower()))


def all_regions() -> Dict[Tuple[str, str], Tuple[float, float]]:
    """All catalogued regions (used by the pre-extraction script)."""
    return dict(_CENTROIDS)
