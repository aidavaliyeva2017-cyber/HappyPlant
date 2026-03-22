"""
database.py — Supabase Integration für HappyPlant Enterprise

Ersetzt SQLite vollständig. Alle Daten landen in Supabase (PostgreSQL).

Setup:
  1. Supabase Projekt anlegen → https://supabase.com
  2. SQL aus supabase_setup.sql im Supabase SQL-Editor ausführen
  3. In config.yaml eintragen:
       supabase_url: "https://muakcpxgujorvadpjxwi.supabase.co"
       supabase_key: "sb_secret_dvyRDX4oQ8csVHrnYDdTuw_OTNdKcx8"
"""

import aiohttp
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("Database")


class Database:
    """
    Async Supabase REST-Client.

    Nutzt die Supabase PostgREST API direkt via aiohttp —
    kein extra SDK nötig, funktioniert auf jedem Python 3.10+.
    """

    def __init__(self, url: str, key: str):
        self.base_url = url.rstrip("/") + "/rest/v1"
        self._headers = {
            "apikey":        key,
            "Authorization": f"Bearer {key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",   # kein Response-Body bei INSERT
        }

    async def init(self):
        """Verbindung testen."""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.base_url}/zones",
                    headers=self._headers,
                    params={"limit": "1"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    if r.status in (200, 206):
                        log.info("✅ Supabase verbunden.")
                    else:
                        log.warning(f"⚠️  Supabase Verbindung: HTTP {r.status}")
        except Exception as e:
            log.error(f"❌ Supabase nicht erreichbar: {e}")

    # ── Sensor-Readings ───────────────────────────────────────

    async def save_sensor_reading(
        self,
        zone_id: str,
        node_id: str,
        soil_moisture: float,
        status: str,
        plant_name: str,
        health_score: Optional[int],
        health_status: Optional[str],
        temperature_c: Optional[float],
    ):
        """Speichert einen einzelnen Sensorwert."""
        await self._insert("sensor_readings", {
            "zone_id":       zone_id,
            "node_id":       node_id,
            "soil_moisture": soil_moisture,
            "status":        status,
            "plant_name":    plant_name,
            "health_score":  health_score,
            "health_status": health_status,
            "temperature_c": temperature_c,
            "recorded_at":   _now(),
        })

    # ── Bewässerungsereignisse ────────────────────────────────

    async def save_watering_event(
        self,
        zone_id: str,
        node_id: str,
        duration_s: int,
        reason: str,
        skipped_by_weather: bool = False,
        water_used_l: float = 0.0,
    ):
        """Speichert ein Bewässerungsereignis (inkl. wetter-bedingte Skips)."""
        await self._insert("watering_events", {
            "zone_id":            zone_id,
            "node_id":            node_id,
            "duration_s":         duration_s,
            "reason":             reason,
            "skipped_by_weather": skipped_by_weather,
            "water_used_l":       water_used_l,
            "occurred_at":        _now(),
        })

    # ── Zonen-Snapshots ───────────────────────────────────────

    async def save_zone_snapshot(self, zone_state, impact_summary=None):
        """
        Speichert Zonen-Zustand + alle Node-Readings + Impact.
        Wird einmal pro Zone-Loop-Zyklus aufgerufen.
        """
        # Jeden Node einzeln speichern
        for node_id, node in zone_state.nodes.items():
            await self.save_sensor_reading(
                zone_id       = zone_state.zone_id,
                node_id       = node_id,
                soil_moisture = node.soil_moisture,
                status        = node.status,
                plant_name    = node.plant_name,
                health_score  = node.health.score if node.health else None,
                health_status = node.health.status.value if node.health else None,
                temperature_c = None,  # kommt aus Wetter-Cache, optional ergänzen
            )

        # Zonen-Snapshot
        await self._insert("zone_snapshots", {
            "zone_id":              zone_state.zone_id,
            "zone_name":            zone_state.name,
            "avg_moisture":         round(zone_state.avg_moisture, 3),
            "status":               zone_state.status,
            "total_waterings":      zone_state.total_waterings,
            "weather_summary":      zone_state.weather_summary,
            "next_watering_reason": zone_state.next_watering_reason,
            "recorded_at":          _now(),
        })

        # Impact-Daten speichern (überschreibt tagesaktuellen Eintrag via UPSERT)
        if impact_summary:
            await self._upsert("water_impact", {
                "date":                      datetime.now(timezone.utc).date().isoformat(),
                "total_water_used_l":        impact_summary.total_water_used_l,
                "water_saved_vs_classic_l":  impact_summary.water_saved_vs_classic_l,
                "water_saved_by_weather_l":  impact_summary.water_saved_by_weather_l,
                "co2_absorbed_kg":           impact_summary.co2_absorbed_kg,
                "skipped_waterings":         impact_summary.skipped_waterings,
                "energy_saved_kwh":          impact_summary.energy_saved_kwh,
                "updated_at":                _now(),
            })

    # ── Abfragen (für Dashboard / Optimierung) ────────────────

    async def get_recent_health(self, zone_id: str, limit: int = 48):
        """
        Letzte Health-Scores für eine Zone (für Mini-Chart im Dashboard).
        """
        return await self._select(
            "sensor_readings",
            filters={"zone_id": f"eq.{zone_id}"},
            columns="recorded_at,node_id,health_score,health_status,soil_moisture",
            order="recorded_at.desc",
            limit=limit,
        )

    async def get_watering_history(self, zone_id: str, days: int = 7):
        """Bewässerungshistorie der letzten N Tage."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return await self._select(
            "watering_events",
            filters={
                "zone_id":    f"eq.{zone_id}",
                "occurred_at": f"gte.{cutoff}",
            },
            columns="occurred_at,node_id,duration_s,reason,skipped_by_weather,water_used_l",
            order="occurred_at.desc",
        )

    async def get_impact_summary(self):
        """Gesamter Water-Impact (für Impact-Tab im Dashboard)."""
        return await self._select(
            "water_impact",
            order="date.desc",
            limit=30,
        )

    # ── Interne HTTP-Helfer ───────────────────────────────────

    async def _insert(self, table: str, data: dict):
        """Fügt einen Datensatz ein."""
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.base_url}/{table}",
                json=data,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status not in (200, 201, 204):
                    body = await r.text()
                    log.error(f"Supabase INSERT [{table}] HTTP {r.status}: {body}")

    async def _upsert(self, table: str, data: dict):
        """Fügt ein oder aktualisiert einen Datensatz (ON CONFLICT UPDATE)."""
        headers = {**self._headers, "Prefer": "resolution=merge-duplicates"}
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.base_url}/{table}",
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status not in (200, 201, 204):
                    body = await r.text()
                    log.error(f"Supabase UPSERT [{table}] HTTP {r.status}: {body}")

    async def _select(self, table: str, filters: dict = None,
                      columns: str = "*", order: str = None, limit: int = None):
        """Liest Datensätze aus Supabase."""
        params = {"select": columns}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)

        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{self.base_url}/{table}",
                headers=self._headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    return await r.json()
                log.error(f"Supabase SELECT [{table}] HTTP {r.status}")
                return []

    async def close(self):
        pass  # aiohttp Sessions werden per-request geöffnet/geschlossen


def _now() -> str:
    """ISO-Timestamp mit Timezone für Supabase."""
    return datetime.now(timezone.utc).isoformat()
