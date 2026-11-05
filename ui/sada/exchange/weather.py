"""Live weather for a persona's location via Open-Meteo (no API key), mapped onto the Weather shape
the UI already uses. Falls back to the persona's mocked values on any error, so the demo never breaks.

Open-Meteo is a free, key-less API. This replaces the 'make it up' weather with a real feed while
keeping the same display contract (summary, temp_c, rain_mm_7d, rain_vs_normal, water_stress, icon).
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import replace

from django.conf import settings

from .catalog import Persona, Weather

_CACHE: dict[str, tuple[float, Weather]] = {}
_TTL = 1800  # 30 min

# WMO weather codes → (summary, icon). Compact mapping of the common buckets.
_WMO = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"), 48: ("Fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Heavy drizzle", "🌧️"),
    61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"),
    80: ("Rain showers", "🌦️"), 81: ("Rain showers", "🌧️"), 82: ("Violent showers", "⛈️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm", "⛈️"), 99: ("Thunderstorm", "⛈️"),
}


def _water_stress(rain_7d: float, temp: float) -> str:
    if rain_7d < 5 and temp >= 22:
        return "High"
    if rain_7d < 20:
        return "Medium"
    return "Low"


def _rain_vs_normal(rain_7d: float) -> str:
    # No climatology here; give an honest, readable relative label from the 7-day total.
    if rain_7d < 5:
        return "well below normal"
    if rain_7d < 20:
        return "below normal"
    if rain_7d < 50:
        return "near normal"
    return "above normal"


def _fetch(lat: float, lon: float) -> Weather:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,weather_code"
        "&daily=precipitation_sum&past_days=7&forecast_days=1&timezone=auto"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "fair-trade-exchange-poc"})
    with urllib.request.urlopen(req, timeout=4) as resp:
        data = json.loads(resp.read().decode())
    temp = round(data["current"]["temperature_2m"])
    code = int(data["current"]["weather_code"])
    summary, icon = _WMO.get(code, ("Current conditions", "🌡️"))
    rains = [r for r in (data.get("daily", {}).get("precipitation_sum") or []) if r is not None]
    rain_7d = round(sum(rains[-7:]))
    return Weather(
        summary=summary, temp_c=temp, rain_mm_7d=rain_7d,
        rain_vs_normal=_rain_vs_normal(rain_7d), water_stress=_water_stress(rain_7d, temp), icon=icon,
    )


def weather_for(persona: Persona) -> Weather:
    """Live weather for the persona's location, cached; the persona's mocked value on any failure."""
    if not getattr(settings, "USE_LIVE_WEATHER", False):
        return persona.weather
    loc = persona.location
    key = f"{loc.lat:.2f},{loc.lon:.2f}"
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        w = _fetch(loc.lat, loc.lon)
        _CACHE[key] = (now, w)
        return w
    except Exception:
        # Keep the demo resilient: fall back to the made-up overlay.
        return persona.weather
