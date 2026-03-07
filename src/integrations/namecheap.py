"""Namecheap API client — domain search, purchase, and nameserver configuration.

Supports .ca, .com, .io, .co TLDs.  The factory uses Namecheap for purchasing
(including .ca which most registrar APIs don't support) and then points NS
records to Cloudflare for DNS management.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_BASE_URL = "https://api.namecheap.com/xml.response"


def _base_params() -> dict:
    return {
        "ApiUser": settings.NAMECHEAP_API_USER,
        "ApiKey": settings.NAMECHEAP_API_KEY,
        "UserName": settings.NAMECHEAP_API_USER,
        "ClientIp": "0.0.0.0",
    }


async def check_domain(domain: str) -> dict:
    """Check if a domain is available.

    Returns {"domain": str, "available": bool, "premium": bool, "price": float | None}.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                _BASE_URL,
                params={
                    **_base_params(),
                    "Command": "namecheap.domains.check",
                    "DomainList": domain,
                },
            )
            resp.raise_for_status()
            body = resp.text

            available = 'Available="true"' in body or "Available='true'" in body
            premium = "IsPremiumName" in body and ('IsPremiumName="true"' in body)

            return {
                "domain": domain,
                "available": available,
                "premium": premium,
                "price": None,
            }
        except Exception as exc:
            logger.error("namecheap_check_failed", domain=domain, error=str(exc))
            return {"domain": domain, "available": False, "premium": False, "price": None, "error": str(exc)}


async def check_domains_batch(domains: list[str]) -> list[dict]:
    """Check availability of multiple domains in one API call (max 50)."""
    results = []
    for chunk in [domains[i : i + 50] for i in range(0, len(domains), 50)]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    _BASE_URL,
                    params={
                        **_base_params(),
                        "Command": "namecheap.domains.check",
                        "DomainList": ",".join(chunk),
                    },
                )
                resp.raise_for_status()
                body = resp.text
                for d in chunk:
                    available = f'Domain="{d}"' in body and 'Available="true"' in body
                    results.append({"domain": d, "available": available})
            except Exception as exc:
                logger.error("namecheap_batch_check_failed", error=str(exc))
                for d in chunk:
                    results.append({"domain": d, "available": False, "error": str(exc)})
    return results


async def purchase_domain(domain: str, *, years: int = 1) -> dict:
    """Purchase a domain via Namecheap.

    Returns {"domain": str, "success": bool, "order_id": str | None, "error": str | None}.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                _BASE_URL,
                params={
                    **_base_params(),
                    "Command": "namecheap.domains.create",
                    "DomainName": domain,
                    "Years": str(years),
                    "RegistrantFirstName": "Factory",
                    "RegistrantLastName": "Labs",
                    "RegistrantAddress1": "Montreal QC",
                    "RegistrantCity": "Montreal",
                    "RegistrantStateProvince": "QC",
                    "RegistrantPostalCode": "H2X1Y4",
                    "RegistrantCountry": "CA",
                    "RegistrantPhone": "+1.5145551234",
                    "RegistrantEmailAddress": "domains@factorylabs.ca",
                    "TechFirstName": "Factory",
                    "TechLastName": "Labs",
                    "TechAddress1": "Montreal QC",
                    "TechCity": "Montreal",
                    "TechStateProvince": "QC",
                    "TechPostalCode": "H2X1Y4",
                    "TechCountry": "CA",
                    "TechPhone": "+1.5145551234",
                    "TechEmailAddress": "domains@factorylabs.ca",
                    "AdminFirstName": "Factory",
                    "AdminLastName": "Labs",
                    "AdminAddress1": "Montreal QC",
                    "AdminCity": "Montreal",
                    "AdminStateProvince": "QC",
                    "AdminPostalCode": "H2X1Y4",
                    "AdminCountry": "CA",
                    "AdminPhone": "+1.5145551234",
                    "AdminEmailAddress": "domains@factorylabs.ca",
                    "AuxBillingFirstName": "Factory",
                    "AuxBillingLastName": "Labs",
                    "AuxBillingAddress1": "Montreal QC",
                    "AuxBillingCity": "Montreal",
                    "AuxBillingStateProvince": "QC",
                    "AuxBillingPostalCode": "H2X1Y4",
                    "AuxBillingCountry": "CA",
                    "AuxBillingPhone": "+1.5145551234",
                    "AuxBillingEmailAddress": "domains@factorylabs.ca",
                },
            )
            resp.raise_for_status()
            body = resp.text

            success = 'Status="OK"' in body or "Registered" in body
            order_id = None
            if "OrderID" in body:
                import re
                match = re.search(r'OrderID="(\d+)"', body)
                order_id = match.group(1) if match else None

            logger.info("namecheap_purchase", domain=domain, success=success, order_id=order_id)
            return {"domain": domain, "success": success, "order_id": order_id, "error": None}

        except Exception as exc:
            logger.error("namecheap_purchase_failed", domain=domain, error=str(exc))
            return {"domain": domain, "success": False, "order_id": None, "error": str(exc)}


async def set_nameservers(domain: str, nameservers: list[str]) -> dict:
    """Point a domain to custom nameservers (e.g. Cloudflare's)."""
    sld, tld = domain.rsplit(".", 1)

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            params = {
                **_base_params(),
                "Command": "namecheap.domains.dns.setCustom",
                "SLD": sld,
                "TLD": tld,
                "Nameservers": ",".join(nameservers),
            }
            resp = await client.get(_BASE_URL, params=params)
            resp.raise_for_status()
            success = 'Status="OK"' in resp.text
            logger.info("namecheap_ns_set", domain=domain, nameservers=nameservers, success=success)
            return {"domain": domain, "success": success}
        except Exception as exc:
            logger.error("namecheap_ns_failed", domain=domain, error=str(exc))
            return {"domain": domain, "success": False, "error": str(exc)}
