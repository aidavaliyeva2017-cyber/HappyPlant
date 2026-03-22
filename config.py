"""
config.py — Systemkonfiguration für HappyPlant Enterprise

Lädt Einstellungen aus config.yaml oder nutzt Standardwerte.
Jede Zone kann eigene Schwellwerte und Geräte haben.
"""

import yaml
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class NodeConfig:
    """Konfiguration eines einzelnen ESP32-CAM Sensors in einer Zone."""
    node_id: str              # z.B. "node_zone1_a"
    mqtt_topic: str           # z.B. "happyplant/zone1/node_a"
    has_camera: bool = True   # Hat dieser Node eine Kamera?
    has_pump: bool = True     # Kann dieser Node eine Pumpe steuern?


@dataclass
class ZoneConfig:
    """Konfiguration einer Bewässerungszone (z.B. Beet, Park-Abschnitt)."""
    zone_id: str                        # eindeutige Zone-ID
    name: str                           # Anzeigename, z.B. "Stadtpark Nord"
    nodes: List[NodeConfig]             # alle Sensoren in dieser Zone

    # Geo-Koordinaten (für Wettervorhersage)
    latitude: float  = 49.1427          # Breitengrad (Default: Heilbronn)
    longitude: float = 9.2109           # Längengrad  (Default: Heilbronn)

    # Schwellwerte für diese Zone
    soil_dry_threshold: float = 0.3     # unter 30% = trocken
    water_duration_s: int = 10          # Gießdauer in Sekunden
    check_interval_s: int = 60          # Prüfintervall in Sekunden
    identify_plant: bool = True         # Pflanzenerkennung aktiv?

    # Wetter-Integration
    use_weather: bool = True            # Wetterprüfung vor dem Gießen?

    # Optionale manuelle Pflanzenzuweisung (überschreibt API)
    plant_override: Optional[str] = None


@dataclass
class SystemConfig:
    """Gesamtkonfiguration des Systems."""
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    plant_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    dashboard_interval_s: int = 10
    weather_cache_minutes: int = 30
    zones: List[ZoneConfig] = field(default_factory=list)

    @staticmethod
    def load(path: str) -> "SystemConfig":
        """Lädt Konfiguration aus YAML-Datei, fällt auf Demo-Config zurück."""
        try:
            with open(path, "r") as f:
                raw = yaml.safe_load(f)
            return SystemConfig._from_dict(raw)
        except FileNotFoundError:
            import logging
            logging.getLogger("Config").warning(
                f"'{path}' nicht gefunden – Demo-Konfiguration wird verwendet."
            )
            return SystemConfig._demo_config()

    @staticmethod
    def _from_dict(raw: dict) -> "SystemConfig":
        zones = []
        for z in raw.get("zones", []):
            nodes = [NodeConfig(**n) for n in z.pop("nodes", [])]
            zones.append(ZoneConfig(nodes=nodes, **z))
        raw.pop("zones", None)
        return SystemConfig(zones=zones, **raw)

    @staticmethod
    def _demo_config() -> "SystemConfig":
        """Demo-Konfiguration mit 3 Zonen und je 2 Nodes."""
        zones = [
            ZoneConfig(
                zone_id="zone_park_nord",
                name="🌳 Stadtpark Nord",
                nodes=[
                    NodeConfig("node_p1", "happyplant/park_nord/node1"),
                    NodeConfig("node_p2", "happyplant/park_nord/node2"),
                ],
                soil_dry_threshold=0.35,
                water_duration_s=15,
                check_interval_s=30,
            ),
            ZoneConfig(
                zone_id="zone_blumenbeete",
                name="🌸 Blumenbeete Marktplatz",
                nodes=[
                    NodeConfig("node_b1", "happyplant/blumenbeete/node1"),
                    NodeConfig("node_b2", "happyplant/blumenbeete/node2", has_camera=False),
                ],
                soil_dry_threshold=0.40,
                water_duration_s=8,
            ),
            ZoneConfig(
                zone_id="zone_gewaechshaus",
                name="🏠 Gewächshaus Betrieb",
                nodes=[
                    NodeConfig("node_g1", "happyplant/gewaechshaus/node1"),
                ],
                soil_dry_threshold=0.25,
                water_duration_s=20,
                check_interval_s=45,
                plant_override="Tomato (Solanum lycopersicum)",
            ),
        ]
        return SystemConfig(
            mqtt_broker="localhost",
            plant_api_key="DEIN_PLANTID_KEY",
            zones=zones,
        )
