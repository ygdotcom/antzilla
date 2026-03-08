"""Instantly.ai API client — cold email account setup and warmup.

Secondary cold-email domains (.io, .co) are configured here.
NEVER the primary .ca domain — that stays clean for transactional email.
Warmup runs for 4-6 weeks at 5-10 emails/day before volume.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_BASE = "https://api.instantly.ai/api/v1"


def _params() -> dict:
    return {"api_key": settings.INSTANTLY_API_KEY}


async def add_sending_account(
    *,
    email: str,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    imap_host: str,
    imap_port: int,
    imap_username: str,
    imap_password: str,
    warmup_enabled: bool = True,
    warmup_limit: int = 5,
) -> dict:
    """Add a sending account to Instantly and optionally enable warmup."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{_BASE}/account/add",
                params=_params(),
                json={
                    "email": email,
                    "smtp_host": smtp_host,
                    "smtp_port": smtp_port,
                    "smtp_username": smtp_username,
                    "smtp_password": smtp_password,
                    "imap_host": imap_host,
                    "imap_port": imap_port,
                    "imap_username": imap_username,
                    "imap_password": imap_password,
                },
            )
            resp.raise_for_status()

            if warmup_enabled:
                await enable_warmup(email=email, daily_limit=warmup_limit)

            logger.info("instantly_account_added", email=email, warmup=warmup_enabled)
            return {"email": email, "success": True, "warmup_enabled": warmup_enabled}

        except Exception as exc:
            logger.error("instantly_add_account_failed", email=email, error=str(exc))
            return {"email": email, "success": False, "error": str(exc)}


async def enable_warmup(*, email: str, daily_limit: int = 5) -> dict:
    """Enable email warmup on a sending account."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{_BASE}/account/warmup/enable",
                params=_params(),
                json={"email": email, "daily_limit": daily_limit},
            )
            resp.raise_for_status()
            return {"email": email, "warmup_enabled": True}
        except Exception as exc:
            logger.warning("instantly_warmup_failed", email=email, error=str(exc))
            return {"email": email, "warmup_enabled": False, "error": str(exc)}


async def get_warmup_status(email: str) -> dict:
    """Check warmup progress for a sending account."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                f"{_BASE}/account/warmup/status",
                params={**_params(), "email": email},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"email": email, "status": "unknown", "error": str(exc)}


async def create_campaign(
    *,
    name: str,
    sending_accounts: list[str],
    subject: str,
    body: str,
    daily_limit: int = 50,
) -> dict:
    """Create a cold email campaign."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{_BASE}/campaign/add",
                params=_params(),
                json={
                    "name": name,
                    "sending_accounts": sending_accounts,
                    "email_list": [],
                    "sequences": [{"subject": subject, "body": body}],
                    "daily_limit": daily_limit,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            campaign_id = data.get("id") or data.get("campaign_id")
            logger.info("instantly_campaign_created", name=name, id=campaign_id)
            return {"campaign_id": campaign_id, "success": True}
        except Exception as exc:
            logger.error("instantly_campaign_failed", name=name, error=str(exc))
            return {"campaign_id": None, "success": False, "error": str(exc)}


async def add_leads_to_campaign(*, campaign_id: str, leads: list[dict]) -> dict:
    """Add leads to an Instantly campaign. Each lead: {"email": ..., "first_name": ..., "company_name": ...}"""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{_BASE}/lead/add",
                params=_params(),
                json={
                    "campaign_id": campaign_id,
                    "skip_if_in_workspace": True,
                    "leads": leads,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("instantly_leads_added", campaign=campaign_id, count=len(leads))
            return {"added": len(leads), "success": True}
        except Exception as exc:
            logger.error("instantly_add_leads_failed", error=str(exc))
            return {"added": 0, "success": False, "error": str(exc)}


async def get_campaign_replies(campaign_id: str) -> list[dict]:
    """Get replies for a campaign."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"{_BASE}/unibox/emails",
                params={**_params(), "campaign_id": campaign_id, "email_type": "received"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as exc:
            logger.warning("instantly_get_replies_failed", error=str(exc))
            return []


async def send_email(*, to_email: str, subject: str, body: str, from_email: str = "",
                     campaign_id: str = "") -> dict:
    """Send a single email via Instantly (add as lead to campaign)."""
    if not campaign_id:
        return {"success": False, "error": "campaign_id required"}

    result = await add_leads_to_campaign(
        campaign_id=campaign_id,
        leads=[{
            "email": to_email,
            "first_name": to_email.split("@")[0],
            "custom_variables": {"subject_override": subject, "body_override": body},
        }],
    )
    return {"success": result.get("success", False), "method": "instantly_campaign"}
