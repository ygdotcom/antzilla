"""Apollo.io API client — people/company enrichment.

Free tier: 50 credits/month. Used in the enrichment waterfall.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_BASE_URL = "https://api.apollo.io/api/v1"


async def enrich_person(*, name: str, company: str, domain: str | None = None) -> dict | None:
    """Enrich a person by name and company.

    Returns {"email", "phone", "title", "company_size", "linkedin_url"} or None.
    """
    if not settings.APOLLO_API_KEY:
        logger.warning("apollo_api_key_not_configured", msg="APOLLO_API_KEY not set")
        return None

    headers = {"x-api-key": settings.APOLLO_API_KEY}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        try:
            payload = {
                "first_name": name.split()[0] if name else "",
                "last_name": " ".join(name.split()[1:]) if name and len(name.split()) > 1 else "",
                "organization_name": company,
                "reveal_personal_emails": True,
            }
            if domain:
                payload["organization_domain"] = domain
            resp = await client.post(f"{_BASE_URL}/people/match", json=payload)
            resp.raise_for_status()
            data = resp.json()
            person = data.get("person")
            if not person:
                return None
            return {
                "email": person.get("email", ""),
                "phone": person.get("phone_numbers", [{}])[0].get("raw_number", "") if person.get("phone_numbers") else "",
                "title": person.get("title", ""),
                "company_size": person.get("organization", {}).get("estimated_num_employees") if person.get("organization") else None,
                "linkedin_url": person.get("linkedin_url", ""),
            }
        except Exception as exc:
            logger.error("apollo_enrich_failed", name=name, company=company, error=str(exc))
            return None


async def search_people(*, domain: str, title_keywords: list[str] | None = None) -> list[dict]:
    """Search for people at a domain, optionally filtered by title keywords."""
    if not settings.APOLLO_API_KEY:
        logger.warning("apollo_api_key_not_configured", msg="APOLLO_API_KEY not set")
        return []

    headers = {"x-api-key": settings.APOLLO_API_KEY}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        try:
            payload = {
                "q_organization_domains": [domain],
            }
            if title_keywords:
                payload["person_titles"] = title_keywords
            resp = await client.post(f"{_BASE_URL}/mixed_people/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
            people = data.get("people", [])
            return people
        except Exception as exc:
            logger.error("apollo_search_failed", domain=domain, error=str(exc))
            return []
