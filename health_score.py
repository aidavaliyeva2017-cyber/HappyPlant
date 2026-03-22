"""
health_score.py — Pflanzengesundheit (0–100 Score)

Berechnet einen Health-Score pro Node basierend auf:
  - Bodenfeuchte (Hauptfaktor)
  - Wie lange der Node schon trocken ist (Stressdauer)
  - Temperatur aus Wetterdaten (Hitzestress)

Status-Einstufung:
  80–100 → healthy   ✅
  50– 79 → warning   ⚠️
   0– 49 → critical  🔴
"""

from dataclasses import dataclass
from enum import Enum


class HealthStatus(Enum):
    HEALTHY  = "healthy"
    WARNING  = "warning"
    CRITICAL = "critical"


@dataclass
class HealthResult:
    score: int                  # 0–100
    status: HealthStatus
    factors: dict               # Einzelbewertungen für Debugging/Dashboard

    @property
    def icon(self) -> str:
        return {
            HealthStatus.HEALTHY:  "✅",
            HealthStatus.WARNING:  "⚠️",
            HealthStatus.CRITICAL: "🔴",
        }[self.status]

    @property
    def label(self) -> str:
        return f"{self.icon} {self.score}/100 ({self.status.value})"


def calculate_health(
    soil_moisture: float,       # 0.0–1.0
    dry_threshold: float,       # Zonen-Schwellwert
    minutes_dry: int = 0,       # wie lange schon trocken (aus DB)
    temperature_c: float = 20.0 # aktuelle Temperatur (aus Wetter-API)
) -> HealthResult:
    """
    Berechnet Health-Score aus mehreren Faktoren.
    Jeder Faktor gibt 0–100 Punkte, gewichtet zusammengerechnet.
    """

    # ── Faktor 1: Bodenfeuchte (Gewicht 60%) ─────────────────
    if soil_moisture >= dry_threshold:
        # Optimal: über Schwellwert
        moisture_score = min(100, int((soil_moisture / 1.0) * 100))
    else:
        # Unter Schwellwert: linear abfallen bis 0
        moisture_score = int((soil_moisture / dry_threshold) * 50)

    # ── Faktor 2: Stressdauer (Gewicht 25%) ──────────────────
    # Je länger trocken, desto schlechter
    if minutes_dry == 0:
        stress_score = 100
    elif minutes_dry < 30:
        stress_score = 80
    elif minutes_dry < 120:
        stress_score = 50
    elif minutes_dry < 360:
        stress_score = 20
    else:
        stress_score = 0        # > 6h trocken = kritisch

    # ── Faktor 3: Temperatur (Gewicht 15%) ───────────────────
    # Ideal: 15–25°C. Darunter/darüber Abzüge.
    if 15 <= temperature_c <= 25:
        temp_score = 100
    elif 10 <= temperature_c < 15 or 25 < temperature_c <= 32:
        temp_score = 70
    elif 5 <= temperature_c < 10 or 32 < temperature_c <= 38:
        temp_score = 40
    else:
        temp_score = 10         # Frost oder Extremhitze

    # ── Gewichteter Gesamtscore ───────────────────────────────
    total = int(
        moisture_score * 0.60 +
        stress_score   * 0.25 +
        temp_score     * 0.15
    )
    total = max(0, min(100, total))

    # ── Status-Einstufung ─────────────────────────────────────
    if total >= 80:
        status = HealthStatus.HEALTHY
    elif total >= 50:
        status = HealthStatus.WARNING
    else:
        status = HealthStatus.CRITICAL

    return HealthResult(
        score=total,
        status=status,
        factors={
            "moisture_score": moisture_score,
            "stress_score":   stress_score,
            "temp_score":     temp_score,
        }
    )
