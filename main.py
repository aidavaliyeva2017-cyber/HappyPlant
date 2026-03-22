"""
╔══════════════════════════════════════════════════════════╗
║         HappyPlant 3.0 — Enterprise Edition              ║
║   Skalierbares Bewässerungssystem für große Grünflächen  ║
╚══════════════════════════════════════════════════════════╝

Features:
  - Mehrere Zonen (Parks, Beete, Gewächshäuser)
  - Wetter-Integration (Open-Meteo, kein Key nötig)
  - Pflanzenerkennung via Plant.id API
  - Health-Score (0–100) pro Pflanze
  - Wasser-Impact & CO₂-Tracking
  - Supabase Cloud-Datenbank
"""

import asyncio
import logging
from config import SystemConfig
from zone_manager import ZoneManager
from database import Database
from dashboard import Dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("HappyPlant")


async def main():
    log.info("🌱 HappyPlant 3.0 Enterprise startet...")

    config = SystemConfig.load("config.yaml")

    # Supabase Datenbank
    db = Database(
        url=config.supabase_url,
        key=config.supabase_key,
    )
    await db.init()

    zone_manager = ZoneManager(config, db)
    await zone_manager.start()

    dashboard = Dashboard(zone_manager, db)

    log.info(f"✅ {len(config.zones)} Zonen geladen. System läuft.")

    try:
        while True:
            dashboard.render()
            await asyncio.sleep(config.dashboard_interval_s)
    except KeyboardInterrupt:
        log.info("System wird beendet...")
        await zone_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
