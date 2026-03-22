"""
seed_data.py — Realistische Testdaten für HappyPlant Supabase

Simuliert 7 Tage Betrieb mit:
  - 3 Zonen, 7 Nodes
  - Stündliche Sensor-Readings (Bodenfeuchte, Health-Score)
  - Bewässerungsereignisse (inkl. wetter-bedingte Skips)
  - Tägliche Water-Impact Werte
  - Zone-Snapshots

Ausführen: python3 seed_data.py
"""

import asyncio
import aiohttp
import random
import yaml
from datetime import datetime, timezone, timedelta

# ── Config laden ──────────────────────────────────────────────
with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

SUPABASE_URL = cfg["supabase_url"].rstrip("/") + "/rest/v1"
SUPABASE_KEY = cfg["supabase_key"]

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

# ── Testdaten Definition ──────────────────────────────────────

ZONES = [
    {
        "zone_id": "zone_park_nord",
        "name":    "🌳 Stadtpark Nord",
        "nodes":   ["node_p1", "node_p2", "node_p3"],
        "plants":  ["Rosa (Rose)", "Lavandula angustifolia (Lavender)", "Buxus sempervirens"],
        "threshold": 0.35,
    },
    {
        "zone_id": "zone_blumenbeete",
        "name":    "🌸 Blumenbeete Marktplatz",
        "nodes":   ["node_b1", "node_b2"],
        "plants":  ["Tulipa (Tulip)", "Bellis perennis (Daisy)"],
        "threshold": 0.40,
    },
    {
        "zone_id": "zone_gewaechshaus",
        "name":    "🏠 Gewächshaus Betrieb",
        "nodes":   ["node_g1", "node_g2"],
        "plants":  ["Solanum lycopersicum (Tomato)", "Cucumis sativus (Cucumber)"],
        "threshold": 0.25,
    },
]

DAYS = 7      # wie viele Tage zurück
HOURS = 24    # Readings pro Tag


async def insert(session, table: str, data):
    """Einzelnen Datensatz einfügen."""
    import ssl
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    async with session.post(
        f"{SUPABASE_URL}/{table}",
        json=data,
        headers=HEADERS,
        ssl=ssl_ctx,
    ) as r:
        if r.status not in (200, 201, 204):
            body = await r.text()
            print(f"  ❌ {table}: HTTP {r.status} — {body[:100]}")


async def seed_sensor_readings(session):
    """Stündliche Sensor-Readings für 7 Tage."""
    print("📊 Sensor-Readings werden eingefügt...")
    count = 0

    for day_offset in range(DAYS, 0, -1):
        for hour in range(0, HOURS, 2):   # alle 2 Stunden
            ts = datetime.now(timezone.utc) - timedelta(days=day_offset, hours=hour)

            for zone in ZONES:
                for i, node_id in enumerate(zone["nodes"]):
                    # Realistische Feuchtigkeitskurve:
                    # morgens trocken, nach Bewässerung feucht, dann wieder trockener
                    base = 0.55 + random.uniform(-0.15, 0.15)
                    if hour < 6:
                        moisture = max(0.1, base - 0.2)   # nachts trockener
                    elif 6 <= hour < 9:
                        moisture = base + 0.2              # nach Morgenbewässerung
                    else:
                        moisture = base

                    moisture = round(min(0.95, max(0.1, moisture)), 2)
                    temp = round(18 + random.uniform(-5, 10), 1)

                    # Health-Score berechnen
                    if moisture >= zone["threshold"]:
                        health = random.randint(75, 98)
                        health_status = "healthy"
                    elif moisture >= zone["threshold"] * 0.7:
                        health = random.randint(45, 74)
                        health_status = "warning"
                    else:
                        health = random.randint(10, 44)
                        health_status = "critical"

                    status = "OK" if moisture >= zone["threshold"] else "DRY"

                    await insert(session, "sensor_readings", {
                        "zone_id":       zone["zone_id"],
                        "node_id":       node_id,
                        "soil_moisture": moisture,
                        "status":        status,
                        "plant_name":    zone["plants"][i % len(zone["plants"])],
                        "health_score":  health,
                        "health_status": health_status,
                        "temperature_c": temp,
                        "recorded_at":   ts.isoformat(),
                    })
                    count += 1

    print(f"  ✅ {count} Sensor-Readings eingefügt")


async def seed_watering_events(session):
    """Bewässerungsereignisse — 2–4x täglich pro Zone."""
    print("💧 Bewässerungsereignisse werden eingefügt...")
    count = 0

    for day_offset in range(DAYS, 0, -1):
        for zone in ZONES:
            # Morgens immer gießen
            for watering_hour in [6, 13, 19]:
                ts = datetime.now(timezone.utc) - timedelta(
                    days=day_offset,
                    hours=random.randint(0, 1),
                    minutes=random.randint(0, 59)
                )
                ts = ts.replace(hour=watering_hour)

                # 20% Chance wegen Regen übersprungen
                skipped = random.random() < 0.20

                node_id = random.choice(zone["nodes"])
                duration = random.randint(8, 20) if not skipped else 0
                water_l  = round(duration * 0.5, 2)

                await insert(session, "watering_events", {
                    "zone_id":            zone["zone_id"],
                    "node_id":            node_id,
                    "duration_s":         duration,
                    "reason":             "Regen erwartet (Open-Meteo)" if skipped else "Boden trocken",
                    "skipped_by_weather": skipped,
                    "water_used_l":       water_l,
                    "occurred_at":        ts.isoformat(),
                })
                count += 1

    print(f"  ✅ {count} Bewässerungsereignisse eingefügt")


async def seed_zone_snapshots(session):
    """Zonen-Snapshots alle 2 Stunden."""
    print("🗂️  Zonen-Snapshots werden eingefügt...")
    count = 0

    for day_offset in range(DAYS, 0, -1):
        for hour in range(0, HOURS, 2):
            ts = datetime.now(timezone.utc) - timedelta(days=day_offset, hours=hour)

            for zone in ZONES:
                avg = round(random.uniform(0.35, 0.75), 2)
                status = "OK" if avg > zone["threshold"] else "DRY"

                await insert(session, "zone_snapshots", {
                    "zone_id":              zone["zone_id"],
                    "zone_name":            zone["name"],
                    "avg_moisture":         avg,
                    "status":               status,
                    "total_waterings":      random.randint(1, 5),
                    "weather_summary":      random.choice([
                        "☀️ NORMAL — Kein Regen erwartet (0.0mm, 19.5°C)",
                        "🌧️ SKIP — Regen in nächsten 6h erwartet (3.2mm)",
                        "☀️ NORMAL — Kein Regen erwartet (0.0mm, 22.1°C)",
                    ]),
                    "next_watering_reason": random.choice([
                        "💧 Boden trocken",
                        "✅ Gerade gegossen",
                        "⏸ Verschoben — Regen erwartet",
                    ]),
                    "recorded_at":          ts.isoformat(),
                })
                count += 1

    print(f"  ✅ {count} Zonen-Snapshots eingefügt")


async def seed_water_impact(session):
    """Tägliche Water-Impact Werte für 7 Tage."""
    print("🌿 Water-Impact Daten werden eingefügt...")
    count = 0

    for day_offset in range(DAYS, 0, -1):
        date = (datetime.now(timezone.utc) - timedelta(days=day_offset)).date()

        water_used      = round(random.uniform(15, 45), 2)
        saved_smart     = round(water_used * 0.5, 2)
        saved_weather   = round(random.uniform(0, 15), 2)
        skipped         = random.randint(0, 5)
        co2             = round(7 * 0.02 * 1, 4)   # 7 Nodes * 0.02kg/Tag
        energy          = round((saved_smart + saved_weather) * 0.001, 4)

        await insert(session, "water_impact", {
            "date":                      date.isoformat(),
            "total_water_used_l":        water_used,
            "water_saved_vs_classic_l":  saved_smart,
            "water_saved_by_weather_l":  saved_weather,
            "co2_absorbed_kg":           co2,
            "skipped_waterings":         skipped,
            "energy_saved_kwh":          energy,
            "updated_at":                datetime.now(timezone.utc).isoformat(),
        })
        count += 1

    print(f"  ✅ {count} Water-Impact Einträge eingefügt")


async def main():
    print("🌱 HappyPlant Seed-Script startet...")
    print(f"   Supabase: {SUPABASE_URL}")
    print(f"   Zeitraum: letzte {DAYS} Tage\n")

    async with aiohttp.ClientSession() as session:
        await seed_sensor_readings(session)
        await seed_watering_events(session)
        await seed_zone_snapshots(session)
        await seed_water_impact(session)

    print("\n✅ Fertig! Alle Testdaten sind in Supabase.")
    print("   → Öffne Supabase Table Editor und refresh die Tabellen.")


if __name__ == "__main__":
    asyncio.run(main())
