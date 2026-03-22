"""
weather_service.py — Wetter-Integration für HappyPlant Enterprise

Nutzt Open-Meteo API (kostenlos, kein API-Key nötig).
Gibt pro Zone eine Bewässerungs-Empfehlung basierend auf
dem Regenvorhersage-Profil der nächsten 6 Stunden zurück.

Entscheidungslogik (binär):
  ┌─────────────────────────────────────────────────────┐
  │  Regen > 0mm in 0–6h  → SKIP   (kein Gießen)       │
  │  Kein Regen in 0–6h   → NORMAL (normal gießen)     │
  └─────────────────────────────────────────────────────┘
"""

import asyncio
import aiohttp
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

log = logging.getLogger("WeatherService")

# Open-Meteo Endpoint (kostenlos, kein Key nötig)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Mindestniederschlag in mm um Gießen zu überspringen
# 0.1mm = jede Spur Regen zählt; erhöhen für "nur bei echtem Regen überspringen"
RAIN_THRESHOLD_MM = 0.1

# Cache-Dauer in Sekunden (Wetter wird nicht jede Minute neu abgefragt)
CACHE_TTL_S = 1800  # 30 Minuten


class WateringDecision(Enum):
    """Bewässerungs-Empfehlung basierend auf Wetterdaten."""
    NORMAL = "NORMAL"   # kein Regen erwartet → normal gießen
    SKIP   = "SKIP"     # Regen erwartet → nicht gießen


@dataclass
class WeatherForecast:
    """Zusammengefasstes Wetter-Ergebnis für eine Zone."""
    decision: WateringDecision
    reason: str                 # menschenlesbare Begründung
    rain_next_6h_mm: float      # Gesamtniederschlag in den nächsten 6h
    temperature_c: float        # aktuelle Temperatur
    fetched_at: datetime        # wann abgefragt

    def should_water(self) -> bool:
        """True wenn Bewässerung stattfinden soll."""
        return self.decision == WateringDecision.NORMAL

    def summary(self) -> str:
        """Kurze Zusammenfassung für Dashboard/Logs."""
        icon = "☀️" if self.should_water() else "🌧️"
        return (
            f"{icon} {self.decision.value} — {self.reason} "
            f"(Regen 6h: {self.rain_next_6h_mm:.1f}mm, {self.temperature_c:.1f}°C)"
        )


class WeatherService:
    """
    Wetterdienst für alle Zonen.

    - Fragt Open-Meteo für jede Zone-Koordinate ab
    - Cached Ergebnisse 30 Minuten (API nicht überlasten)
    - Gibt WateringDecision zurück, die zone_manager.py nutzt
    """

    def __init__(self):
        # Cache: zone_id → (WeatherForecast, timestamp)
        self._cache: dict[str, tuple[WeatherForecast, float]] = {}

    async def get_forecast(self, zone_id: str, lat: float, lon: float) -> WeatherForecast:
        """
        Gibt Wettervorhersage für eine Zone zurück.
        Nutzt Cache falls noch aktuell (< 30 min alt).
        """
        import time
        cached = self._cache.get(zone_id)
        if cached:
            forecast, ts = cached
            if time.time() - ts < CACHE_TTL_S:
                log.debug(f"[{zone_id}] Wetter aus Cache: {forecast.summary()}")
                return forecast

        forecast = await self._fetch_forecast(zone_id, lat, lon)
        self._cache[zone_id] = (forecast, time.time())
        return forecast

    async def _fetch_forecast(self, zone_id: str, lat: float, lon: float) -> WeatherForecast:
        """Ruft Open-Meteo API ab und wertet Niederschlagsdaten aus."""
        params = {
            "latitude":              lat,
            "longitude":             lon,
            "hourly":                "precipitation,temperature_2m",
            "forecast_days":         2,
            "timezone":              "auto",   # automatische Zeitzone
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    OPEN_METEO_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        log.warning(f"[{zone_id}] Open-Meteo HTTP {resp.status} → NORMAL fallback")
                        return self._fallback_forecast()

                    data = await resp.json()

            return self._parse_forecast(zone_id, data)

        except asyncio.TimeoutError:
            log.warning(f"[{zone_id}] Open-Meteo Timeout → NORMAL fallback")
            return self._fallback_forecast()
        except Exception as e:
            log.error(f"[{zone_id}] Wetter-Fehler: {e} → NORMAL fallback")
            return self._fallback_forecast()

    def _parse_forecast(self, zone_id: str, data: dict) -> WeatherForecast:
        """
        Wertet stündliche Niederschlagsdaten für die nächsten 6h aus.

        Open-Meteo liefert:
          hourly.time           → Liste von ISO-Zeitstempeln
          hourly.precipitation  → Niederschlag in mm/h pro Stunde
          hourly.temperature_2m → Temperatur in °C
        """
        hourly = data.get("hourly", {})
        times  = hourly.get("time", [])
        precip = hourly.get("precipitation", [])
        temps  = hourly.get("temperature_2m", [])

        now         = datetime.now(timezone.utc)
        rain_6h     = 0.0
        current_temp = temps[0] if temps else 20.0

        for i, time_str in enumerate(times):
            if i >= len(precip):
                break
            try:
                hour_dt = datetime.fromisoformat(time_str)
                if hour_dt.tzinfo is None:
                    hour_dt = hour_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            hours_from_now = (hour_dt - now).total_seconds() / 3600

            if 0 <= hours_from_now <= 6:
                rain_6h += precip[i]
            if i == 0 and temps:
                current_temp = temps[i]

        # ── Binäre Entscheidung ───────────────────────────────
        if rain_6h >= RAIN_THRESHOLD_MM:
            decision = WateringDecision.SKIP
            reason   = f"Regen in nächsten 6h erwartet ({rain_6h:.1f}mm)"
        else:
            decision = WateringDecision.NORMAL
            reason   = "Kein Regen in nächsten 6h erwartet"

        forecast = WeatherForecast(
            decision        = decision,
            reason          = reason,
            rain_next_6h_mm = round(rain_6h, 2),
            temperature_c   = round(current_temp, 1),
            fetched_at      = now,
        )

        log.info(f"[{zone_id}] Wetter: {forecast.summary()}")
        return forecast

    def _fallback_forecast(self) -> WeatherForecast:
        """
        Fallback wenn API nicht erreichbar:
        NORMAL → lieber gießen als Pflanze verdursten lassen.
        """
        return WeatherForecast(
            decision        = WateringDecision.NORMAL,
            reason          = "Wetter-API nicht erreichbar (Fallback)",
            rain_next_6h_mm = 0.0,
            temperature_c   = 20.0,
            fetched_at      = datetime.now(timezone.utc),
        )
