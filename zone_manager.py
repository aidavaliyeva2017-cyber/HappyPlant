"""
zone_manager.py — Verwaltet alle Bewässerungszonen

Jede Zone läuft als eigener asyncio-Task.
Kommunikation mit ESP32-Nodes über MQTT (simuliert oder echt).
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from config import SystemConfig, ZoneConfig
from database import Database
from plant_identifier import PlantIdentifier
from weather_service import WeatherService, WateringDecision
from health_score import calculate_health, HealthResult, HealthStatus
from water_impact import WaterImpactTracker

log = logging.getLogger("ZoneManager")


@dataclass
class NodeState:
    """Aktueller Zustand eines einzelnen Sensor-Nodes."""
    node_id: str
    soil_moisture: float = 0.5
    is_watering: bool = False
    last_seen: datetime = field(default_factory=datetime.now)
    plant_name: str = "Unbekannt"
    status: str = "OK"              # OK | DRY | WATERING | OFFLINE
    health: Optional[HealthResult] = None
    minutes_dry: int = 0            # wie lange schon trocken (für Health-Score)


@dataclass
class ZoneState:
    """Aktueller Zustand einer ganzen Zone."""
    zone_id: str
    name: str
    nodes: Dict[str, NodeState] = field(default_factory=dict)
    avg_moisture: float = 0.5
    total_waterings: int = 0
    last_watered: Optional[datetime] = None
    next_watering_reason: str = "—"     # z.B. "Boden trocken" oder "verschoben: Regen"
    status: str = "OK"
    weather_summary: str = "—"


class ZoneManager:
    """
    Zentrale Steuerung aller Zonen.
    Enthält: Sensoren, Pflanzenerkennung, Wetter, Health-Score, Water-Impact.
    """

    def __init__(self, config: SystemConfig, db: Database):
        self.config = config
        self.db = db
        self.plant_id  = PlantIdentifier(config.plant_api_key)
        self.weather   = WeatherService()
        self.impact    = WaterImpactTracker()
        self.zones: Dict[str, ZoneState] = {}
        self._tasks: List[asyncio.Task] = []
        self._running = False

    async def start(self):
        """Alle Zonen-Tasks starten."""
        self._running = True

        total_nodes = sum(len(z.nodes) for z in self.config.zones)
        self.impact.set_plant_count(total_nodes)

        for zone_cfg in self.config.zones:
            self.zones[zone_cfg.zone_id] = ZoneState(
                zone_id=zone_cfg.zone_id,
                name=zone_cfg.name,
                nodes={
                    node.node_id: NodeState(node_id=node.node_id)
                    for node in zone_cfg.nodes
                }
            )

        for zone_cfg in self.config.zones:
            task = asyncio.create_task(
                self._zone_loop(zone_cfg),
                name=f"zone_{zone_cfg.zone_id}"
            )
            self._tasks.append(task)

        log.info(f"✅ {len(self._tasks)} Zonen-Tasks gestartet.")

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        log.info("Alle Zonen gestoppt.")

    # ─────────────────────────────────────────────────────────
    # Zonen-Loop
    # ─────────────────────────────────────────────────────────

    async def _zone_loop(self, zone_cfg: ZoneConfig):
        log.info(f"[{zone_cfg.name}] Zone-Loop gestartet.")

        while self._running:
            try:
                zone_state = self.zones[zone_cfg.zone_id]

                # 1. Sensordaten lesen
                await self._read_all_nodes(zone_cfg, zone_state)

                # 2. Pflanzenerkennung
                await self._identify_plants(zone_cfg, zone_state)

                # 3. Wetter holen
                forecast = None
                if zone_cfg.use_weather:
                    forecast = await self.weather.get_forecast(
                        zone_cfg.zone_id,
                        zone_cfg.latitude,
                        zone_cfg.longitude,
                    )
                    zone_state.weather_summary = forecast.summary()

                # 4. Health-Score berechnen
                temp = forecast.temperature_c if forecast else 20.0
                self._update_health(zone_cfg, zone_state, temp)

                # 5. Bewässerungsentscheidung
                await self._decide_watering(zone_cfg, zone_state, forecast)

                # 6. Statistiken
                self._update_zone_stats(zone_state)

                # 7. In Datenbank speichern
                await self.db.save_zone_snapshot(zone_state, self.impact.calculate_impact())

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[{zone_cfg.name}] Fehler: {e}")

            await asyncio.sleep(zone_cfg.check_interval_s)

    # ─────────────────────────────────────────────────────────
    # Sensoren
    # ─────────────────────────────────────────────────────────

    async def _read_all_nodes(self, zone_cfg: ZoneConfig, zone_state: ZoneState):
        for node_cfg in zone_cfg.nodes:
            moisture = await self._read_sensor(node_cfg.mqtt_topic)
            node_state = zone_state.nodes[node_cfg.node_id]
            node_state.soil_moisture = moisture
            node_state.last_seen = datetime.now()

            if moisture < zone_cfg.soil_dry_threshold:
                node_state.status = "DRY"
                node_state.minutes_dry += zone_cfg.check_interval_s // 60
            else:
                node_state.status = "OK"
                node_state.minutes_dry = 0  # reset wenn wieder feucht

    async def _read_sensor(self, mqtt_topic: str) -> float:
        """
        PRODUKTION: echte MQTT-Nachricht lesen
        SIMULATION: zufälliger Wert
        """
        await asyncio.sleep(0.05)
        return round(random.uniform(0.1, 0.9), 2)

    # ─────────────────────────────────────────────────────────
    # Pflanzenerkennung
    # ─────────────────────────────────────────────────────────

    async def _identify_plants(self, zone_cfg: ZoneConfig, zone_state: ZoneState):
        if not zone_cfg.identify_plant:
            return
        if zone_cfg.plant_override:
            for node_state in zone_state.nodes.values():
                node_state.plant_name = zone_cfg.plant_override
            return
        for node_cfg in zone_cfg.nodes:
            if not node_cfg.has_camera:
                continue
            node_state = zone_state.nodes[node_cfg.node_id]
            plant_name = await self.plant_id.identify(node_cfg.node_id)
            if plant_name != "unknown":
                node_state.plant_name = plant_name

    # ─────────────────────────────────────────────────────────
    # Health-Score
    # ─────────────────────────────────────────────────────────

    def _update_health(self, zone_cfg: ZoneConfig, zone_state: ZoneState, temperature_c: float):
        """Berechnet Health-Score für jeden Node in der Zone."""
        for node_state in zone_state.nodes.values():
            node_state.health = calculate_health(
                soil_moisture  = node_state.soil_moisture,
                dry_threshold  = zone_cfg.soil_dry_threshold,
                minutes_dry    = node_state.minutes_dry,
                temperature_c  = temperature_c,
            )

    # ─────────────────────────────────────────────────────────
    # Bewässerungsentscheidung
    # ─────────────────────────────────────────────────────────

    async def _decide_watering(self, zone_cfg: ZoneConfig, zone_state: ZoneState, forecast=None):
        # Regen erwartet → überspringen + Impact tracken
        if forecast and not forecast.should_water():
            zone_state.next_watering_reason = f"⏸ Verschoben — {forecast.reason}"
            log.info(f"[{zone_cfg.name}] 🌧️ Bewässerung verschoben — {forecast.reason}")
            for node_cfg in zone_cfg.nodes:
                if zone_state.nodes[node_cfg.node_id].status == "DRY":
                    self.impact.record_skipped(zone_cfg.zone_id, node_cfg.node_id)
            return

        for node_cfg in zone_cfg.nodes:
            if not node_cfg.has_pump:
                continue
            node_state = zone_state.nodes[node_cfg.node_id]
            if node_state.status == "DRY" and not node_state.is_watering:
                zone_state.next_watering_reason = "💧 Boden trocken"
                asyncio.create_task(
                    self._water_node(node_cfg, node_state, zone_cfg, zone_state)
                )

    async def _water_node(self, node_cfg, node_state: NodeState,
                          zone_cfg: ZoneConfig, zone_state: ZoneState):
        duration_s = zone_cfg.water_duration_s
        log.info(f"[{zone_cfg.name}] 💧 {node_cfg.node_id} — {duration_s}s")

        node_state.is_watering = True
        node_state.status = "WATERING"
        zone_state.status = "WATERING"

        await self._send_pump_command(node_cfg.mqtt_topic, True)
        await asyncio.sleep(duration_s)
        await self._send_pump_command(node_cfg.mqtt_topic, False)

        node_state.is_watering = False
        node_state.status = "OK"
        node_state.minutes_dry = 0
        zone_state.total_waterings += 1
        zone_state.last_watered = datetime.now()
        zone_state.next_watering_reason = "✅ Gerade gegossen"

        # Impact tracken
        self.impact.record_watering(zone_cfg.zone_id, node_cfg.node_id, duration_s)
        log.info(f"[{zone_cfg.name}] ✅ Bewässerung beendet: {node_cfg.node_id}")

    async def _send_pump_command(self, mqtt_topic: str, on: bool):
        await asyncio.sleep(0.02)
        log.debug(f"MQTT → {mqtt_topic}/pump = {'ON' if on else 'OFF'}")

    # ─────────────────────────────────────────────────────────
    # Statistik
    # ─────────────────────────────────────────────────────────

    def _update_zone_stats(self, zone_state: ZoneState):
        if not zone_state.nodes:
            return
        values = [n.soil_moisture for n in zone_state.nodes.values()]
        zone_state.avg_moisture = sum(values) / len(values)

        statuses = {n.status for n in zone_state.nodes.values()}
        if "WATERING" in statuses:
            zone_state.status = "WATERING"
        elif all(s == "OK" for s in statuses):
            zone_state.status = "OK"
        elif "DRY" in statuses:
            zone_state.status = "DRY"
