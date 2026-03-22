"""
water_impact.py — Wasser-Impact & Klimabeitrag

Berechnet:
  - Wie viel Wasser durch smarte Bewässerung eingespart wurde
    (Vergleich: klassische Zeitschaltuhr vs. sensorgesteuert)
  - CO₂-Absorptionsschätzung der bewässerten Pflanzen
  - Beitrag zum Urban Greening

Grundannahmen (konservativ, wissenschaftlich belegt):
  - Klassische Bewässerung: ~4L/m² pro Gießvorgang
  - Smarte Bewässerung: nur wenn Sensor trocken → ~50% Einsparung
  - Durchschnittliche Stadtpflanze: 0.02 kg CO₂/Tag absorbiert
  - 1L Wasser eingespart ≈ 0.001 kWh Pumpenenergie gespart
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


# ── Konstanten ────────────────────────────────────────────────
LITERS_PER_SECOND_PUMP   = 0.5     # Pumpenleistung: 0.5L/s (typische Mini-Pumpe)
CLASSIC_WATERING_L_PER_M2 = 4.0   # konventionelle Bewässerung pro Gießgang
SMART_SAVING_FACTOR       = 0.50   # smarte Bewässerung spart ~50% Wasser
CO2_PER_PLANT_PER_DAY_KG  = 0.02  # CO₂-Absorption pro Pflanze/Tag
KWH_PER_LITER_SAVED       = 0.001  # Energieeinsparung durch weniger Pumpen


@dataclass
class WateringEvent:
    """Ein einzelnes Bewässerungsereignis."""
    timestamp: datetime
    zone_id: str
    node_id: str
    duration_s: int
    skipped_by_weather: bool = False   # wegen Regen übersprungen


@dataclass
class ImpactSummary:
    """Zusammengefasster Klima- und Wasserbeitrag."""
    total_water_used_l: float          # tatsächlich verbrauchtes Wasser
    water_saved_vs_classic_l: float    # Einsparung gegenüber Zeitschaltuhr
    co2_absorbed_kg: float             # CO₂ absorbiert durch bewässerte Pflanzen
    skipped_waterings: int             # Gießvorgänge die Regen eingespart hat
    water_saved_by_weather_l: float    # Wasser gespart durch Regen-Skip
    energy_saved_kwh: float            # Energieeinsparung gesamt
    period_days: int                   # Zeitraum der Berechnung

    def total_saved_l(self) -> float:
        return self.water_saved_vs_classic_l + self.water_saved_by_weather_l

    def summary_lines(self) -> List[str]:
        return [
            f"💧 Wasser verbraucht:      {self.total_water_used_l:.1f} L",
            f"💰 Eingespart vs. klassisch: {self.water_saved_vs_classic_l:.1f} L ({SMART_SAVING_FACTOR*100:.0f}%)",
            f"🌧️  Eingespart durch Regen:  {self.water_saved_by_weather_l:.1f} L ({self.skipped_waterings}x übersprungen)",
            f"🌿 CO₂ absorbiert:          {self.co2_absorbed_kg:.3f} kg",
            f"⚡ Energie eingespart:       {self.energy_saved_kwh:.4f} kWh",
            f"📅 Zeitraum:               {self.period_days} Tag(e)",
        ]


class WaterImpactTracker:
    """
    Verfolgt alle Bewässerungsereignisse und berechnet den Klima-Impact.

    Wird vom ZoneManager bei jedem Gießvorgang und jedem
    wetterbedingt übersprungenen Vorgang befüllt.
    """

    def __init__(self):
        self._events: List[WateringEvent] = []
        self._plant_count: int = 0          # Gesamtzahl bewässerter Pflanzen
        self._start: datetime = datetime.now()

    def set_plant_count(self, count: int):
        """Gesamtzahl der Pflanzen im System setzen."""
        self._plant_count = count

    def record_watering(self, zone_id: str, node_id: str, duration_s: int):
        """Bewässerungsereignis registrieren."""
        self._events.append(WateringEvent(
            timestamp=datetime.now(),
            zone_id=zone_id,
            node_id=node_id,
            duration_s=duration_s,
            skipped_by_weather=False,
        ))

    def record_skipped(self, zone_id: str, node_id: str):
        """
        Übersprungene Bewässerung wegen Regen registrieren.
        Dauer wird als konfigurierte Standard-Gießdauer angenommen.
        """
        self._events.append(WateringEvent(
            timestamp=datetime.now(),
            zone_id=zone_id,
            node_id=node_id,
            duration_s=10,              # geschätzte Dauer die eingespart wurde
            skipped_by_weather=True,
        ))

    def calculate_impact(self) -> ImpactSummary:
        """Berechnet den gesamten Klima- und Wasser-Impact."""
        period_days = max(1, (datetime.now() - self._start).days)

        # Tatsächlich verbrauchtes Wasser
        actual_events    = [e for e in self._events if not e.skipped_by_weather]
        skipped_events   = [e for e in self._events if e.skipped_by_weather]

        water_used_l     = sum(e.duration_s * LITERS_PER_SECOND_PUMP for e in actual_events)

        # Klassische Zeitschaltuhr hätte ungefähr doppelt so viel gebraucht
        classic_water_l  = water_used_l / (1 - SMART_SAVING_FACTOR)
        saved_smart_l    = classic_water_l - water_used_l

        # Durch Regen übersprungenes Wasser
        saved_weather_l  = sum(
            e.duration_s * LITERS_PER_SECOND_PUMP for e in skipped_events
        )

        # CO₂-Absorption aller Pflanzen
        co2_kg = self._plant_count * CO2_PER_PLANT_PER_DAY_KG * period_days

        # Energieeinsparung
        total_saved_l    = saved_smart_l + saved_weather_l
        energy_saved_kwh = total_saved_l * KWH_PER_LITER_SAVED

        return ImpactSummary(
            total_water_used_l       = round(water_used_l, 2),
            water_saved_vs_classic_l = round(saved_smart_l, 2),
            co2_absorbed_kg          = round(co2_kg, 4),
            skipped_waterings        = len(skipped_events),
            water_saved_by_weather_l = round(saved_weather_l, 2),
            energy_saved_kwh         = round(energy_saved_kwh, 4),
            period_days              = period_days,
        )
