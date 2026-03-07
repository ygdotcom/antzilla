"""Twilio client — SMS sending and phone number management.

Used for: dunning SMS, referral reminders, onboarding nudges,
and as the telephony layer for Retell AI voice calls.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_BASE = "https://api.twilio.com/2010-04-01"


def _auth() -> tuple[str, str]:
    return settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN


async def send_sms(*, to: str, body: str, from_number: str | None = None) -> dict:
    """Send an SMS via Twilio."""
    if not settings.TWILIO_ACCOUNT_SID:
        return {"sid": None, "status": "skipped", "reason": "no credentials"}

    from_num = from_number or settings.TWILIO_PHONE_NUMBER
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{_BASE}/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                auth=_auth(),
                data={"From": from_num, "To": to, "Body": body},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("twilio_sms_sent", to=to[:7] + "...", sid=data.get("sid"))
            return {"sid": data.get("sid"), "status": data.get("status", "sent")}
        except Exception as exc:
            logger.error("twilio_sms_failed", to=to[:7] + "...", error=str(exc))
            return {"sid": None, "status": "error", "error": str(exc)}


async def lookup_number(phone: str) -> dict:
    """Look up a phone number for carrier/type info."""
    if not settings.TWILIO_ACCOUNT_SID:
        return {"valid": False}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                f"https://lookups.twilio.com/v2/PhoneNumbers/{phone}",
                auth=_auth(),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "valid": data.get("valid", False),
                "country_code": data.get("country_code"),
                "carrier": data.get("carrier", {}).get("name"),
                "type": data.get("carrier", {}).get("type"),
            }
        except Exception:
            return {"valid": False}
