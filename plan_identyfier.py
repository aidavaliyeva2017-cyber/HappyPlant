"""
plant_identifier.py — Pl@ntNet API Integration (kostenlos, 500/Tag)

Ersetzt Plant.id mit der kostenlosen Pl@ntNet API.
API Docs: https://my.plantnet.org/
"""

import asyncio
import logging
import aiohttp
import base64
import time
from typing import Dict, Tuple

log = logging.getLogger("PlantIdentifier")

PLANTNET_API_URL = "https://my-api.plantnet.org/v2/identify/all"

DEMO_PLANTS = [
    "Rosa (Rose)",
    "Lavandula angustifolia (Lavender)",
    "Buxus sempervirens (Common Boxwood)",
    "Hedera helix (Common Ivy)",
    "Taxus baccata (English Yew)",
]


class PlantIdentifier:
    """
    Pflanzenerkennung via Pl@ntNet API.
    - Kostenlos bis 500 Anfragen/Tag
    - 24h Cache pro Node (API nicht verschwenden)
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._cache: Dict[str, Tuple[str, float]] = {}
        self._cache_ttl_s = 86400   # 24 Stunden

    async def identify(self, node_id: str, image_bytes: bytes = None) -> str:
        """
        Identifiziert eine Pflanze für einen Node.
        Ohne Bild oder API Key → Demo-Modus.
        """
        cached = self._get_cached(node_id)
        if cached:
            return cached

        if not self.api_key or self.api_key == "DEIN_PLANTID_KEY" or not image_bytes:
            return await self._demo_identify(node_id)

        return await self._api_identify(node_id, image_bytes)

    async def _api_identify(self, node_id: str, image_bytes: bytes) -> str:
        """Echter Pl@ntNet API-Call via multipart/form-data."""
        try:
            # Pl@ntNet erwartet multipart Form-Data mit dem Bild
            form = aiohttp.FormData()
            form.add_field(
                "images",
                image_bytes,
                filename="plant.jpg",
                content_type="image/jpeg",
            )

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    PLANTNET_API_URL,
                    data=form,
                    params={
                        "api-key": self.api_key,
                        "lang":    "de",          # Deutsch
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        log.warning(f"Pl@ntNet HTTP {resp.status}")
                        return "unknown"

                    data = await resp.json()
                    results = data.get("results", [])

                    if not results:
                        return "unknown"

                    # Bester Treffer: wissenschaftlicher Name + deutsche Bezeichnung
                    best = results[0]
                    sci_name    = best.get("species", {}).get("scientificNameWithoutAuthor", "")
                    common_names = best.get("species", {}).get("commonNames", [])
                    common       = common_names[0] if common_names else ""

                    plant_name = f"{common} ({sci_name})" if common else sci_name
                    if not plant_name:
                        return "unknown"

                    self._set_cache(node_id, plant_name)
                    log.info(f"Pl@ntNet erkannt: {plant_name}")
                    return plant_name

        except asyncio.TimeoutError:
            log.warning(f"Pl@ntNet Timeout für {node_id}")
            return "unknown"
        except Exception as e:
            log.error(f"Pl@ntNet Fehler für {node_id}: {e}")
            return "unknown"

    async def _demo_identify(self, node_id: str) -> str:
        """Demo-Modus wenn kein API Key oder kein Bild."""
        await asyncio.sleep(0.1)
        import random
        plant = random.choice(DEMO_PLANTS)
        self._set_cache(node_id, plant)
        return plant

    def _get_cached(self, node_id: str):
        if node_id not in self._cache:
            return None
        name, ts = self._cache[node_id]
        if time.time() - ts > self._cache_ttl_s:
            del self._cache[node_id]
            return None
        return name

    def _set_cache(self, node_id: str, plant_name: str):
        self._cache[node_id] = (plant_name, time.time())
