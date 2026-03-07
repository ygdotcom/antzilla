"""Hunter.io API client — domain email finding.

Used in the enrichment waterfall for domain-based email discovery.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_BASE_URL = "https://api.hunter.io/v2"


async def find_email(*, domain: str, first_name: str | None = None, last_name: str | None = None) -> dict | None:
    """Find email for a person at a domain.

    Returns {"email", "confidence", "sources"} or None.
    """
    if not settings.HUNTER_API_KEY:
        logger.warning("hunter_api_key_not_configured", msg="HUNTER_API_KEY not set")
        return None

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            params = {"domain": domain, "api_key": settings.HUNTER_API_KEY}
            if first_name:
                params["first_name"] = first_name
            if last_name:
                params["last_name"] = last_name
            resp = await client.get(f"{_BASE_URL}/email-finder", params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("data") and data["data"].get("email"):
                d = data["data"]
                return {
                    "email": d.get("email", ""),
                    "confidence": d.get("score", 0),
                    "sources": d.get("sources", []),
                }
            return None
        except Exception as exc:
            logger.error("hunter_find_email_failed", domain=domain, error=str(exc))
            return None


async def domain_search(domain: str) -> list[dict]:
    """Search for all emails at a domain.

    Returns list of {"email", "first_name", "last_name", "position", "confidence"}.
    """
    if not settings.HUNTER_API_KEY:
        logger.warning("hunter_api_key_not_configured", msg="HUNTER_API_KEY not set")
        return []

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"{_BASE_URL}/domain-search",
                params={"domain": domain, "api_key": settings.HUNTER_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()
            emails = data.get("data", {}).get("emails", [])
            return [
                {
                    "email": e.get("value", ""),
                    "first_name": e.get("first_name", ""),
                    "last_name": e.get("last_name", ""),
                    "position": e.get("position", ""),
                    "confidence": e.get("confidence", 0),
                }
                for e in emails
            ]
        except Exception as exc:
            logger.error("hunter_domain_search_failed", domain=domain, error=str(exc))
            return []
