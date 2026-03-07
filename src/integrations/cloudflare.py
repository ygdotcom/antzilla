"""Cloudflare API client — DNS zone management, record creation, email routing.

Manages DNS for all factory business domains: A records, MX, SPF, DKIM, DMARC.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_BASE = "https://api.cloudflare.com/client/v4"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }


async def create_zone(domain: str) -> dict:
    """Add a domain to Cloudflare. Returns zone_id and assigned nameservers."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{_BASE}/zones",
                headers=_headers(),
                json={"name": domain, "type": "full"},
            )
            data = resp.json()
            if data.get("success"):
                zone = data["result"]
                logger.info("cf_zone_created", domain=domain, zone_id=zone["id"])
                return {
                    "domain": domain,
                    "zone_id": zone["id"],
                    "nameservers": zone.get("name_servers", []),
                    "success": True,
                }
            errors = data.get("errors", [])
            # Zone may already exist
            if any(e.get("code") == 1061 for e in errors):
                zones = await list_zones(domain)
                if zones:
                    return {**zones[0], "success": True}
            logger.error("cf_zone_failed", domain=domain, errors=errors)
            return {"domain": domain, "zone_id": None, "nameservers": [], "success": False, "errors": errors}
        except Exception as exc:
            logger.error("cf_zone_error", domain=domain, error=str(exc))
            return {"domain": domain, "zone_id": None, "nameservers": [], "success": False, "error": str(exc)}


async def list_zones(domain: str) -> list[dict]:
    """List Cloudflare zones matching a domain."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_BASE}/zones",
            headers=_headers(),
            params={"name": domain},
        )
        data = resp.json()
        if data.get("success"):
            return [
                {"domain": z["name"], "zone_id": z["id"], "nameservers": z.get("name_servers", [])}
                for z in data.get("result", [])
            ]
    return []


async def create_dns_record(
    zone_id: str,
    *,
    record_type: str,
    name: str,
    content: str,
    ttl: int = 1,
    proxied: bool = False,
    priority: int | None = None,
) -> dict:
    """Create a DNS record in a Cloudflare zone."""
    payload: dict = {
        "type": record_type,
        "name": name,
        "content": content,
        "ttl": ttl,
        "proxied": proxied,
    }
    if priority is not None:
        payload["priority"] = priority

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{_BASE}/zones/{zone_id}/dns_records",
                headers=_headers(),
                json=payload,
            )
            data = resp.json()
            if data.get("success"):
                record = data["result"]
                return {"id": record["id"], "type": record_type, "name": name, "success": True}
            return {"type": record_type, "name": name, "success": False, "errors": data.get("errors")}
        except Exception as exc:
            return {"type": record_type, "name": name, "success": False, "error": str(exc)}


async def setup_email_dns(zone_id: str, domain: str) -> list[dict]:
    """Set up MX + SPF + DMARC records for email sending on a domain."""
    results = []

    # MX for receiving (optional — points to mail provider)
    results.append(
        await create_dns_record(
            zone_id, record_type="MX", name=domain, content=f"mx.{domain}", priority=10
        )
    )

    # SPF — allow common senders
    results.append(
        await create_dns_record(
            zone_id,
            record_type="TXT",
            name=domain,
            content="v=spf1 include:_spf.google.com include:sendgrid.net include:amazonses.com ~all",
        )
    )

    # DMARC
    results.append(
        await create_dns_record(
            zone_id,
            record_type="TXT",
            name=f"_dmarc.{domain}",
            content=f"v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}; pct=100",
        )
    )

    logger.info("cf_email_dns_setup", domain=domain, records=len(results))
    return results


async def setup_vercel_dns(zone_id: str, domain: str) -> list[dict]:
    """Point domain to Vercel (CNAME for www, A for apex)."""
    results = []
    results.append(
        await create_dns_record(
            zone_id, record_type="A", name=domain, content="76.76.21.21", proxied=True
        )
    )
    results.append(
        await create_dns_record(
            zone_id, record_type="CNAME", name=f"www.{domain}", content="cname.vercel-dns.com", proxied=True
        )
    )
    return results
