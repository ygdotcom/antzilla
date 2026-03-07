"""Serper Maps API client — Google Maps lead discovery.

Cost: $0.20/1000 results. Used for local business lead discovery.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_BASE_URL = "https://google.serper.dev/maps"


async def search_maps(query: str, location: str, *, num: int = 20) -> list[dict]:
    """Search Google Maps via Serper API.

    Returns list of {"name", "phone", "website", "address", "rating", "reviews", "place_id"}.
    """
    if not settings.SERPER_API_KEY:
        logger.warning("serper_api_key_not_configured", msg="SERPER_API_KEY not set, returning empty list")
        return []

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                _BASE_URL,
                json={"q": query, "location": location, "num": num},
                headers={"X-API-KEY": settings.SERPER_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()
            places = data.get("places", [])
            results = []
            for p in places:
                results.append({
                    "name": p.get("title") or p.get("name", ""),
                    "phone": p.get("phone", ""),
                    "website": p.get("website", ""),
                    "address": p.get("address", ""),
                    "rating": p.get("rating"),
                    "reviews": p.get("reviews"),
                    "place_id": p.get("place_id", ""),
                })
            return results
        except Exception as exc:
            logger.error("serper_maps_failed", query=query, location=location, error=str(exc))
            return []
