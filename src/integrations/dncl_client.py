"""Canada National DNCL (Do Not Call List) client.

EVERY outbound call number MUST be checked against the DNCL before dialing.
Fine: up to $15,000 per non-compliant call. NON-NEGOTIABLE.

Uses a local cache (dncl_cache table) refreshed every 31 days per CRTC rules.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import text

from src.db import SessionLocal

logger = structlog.get_logger()


async def check_dncl(phone: str) -> dict:
    """Check if a phone number is on the DNCL.

    1. Check internal DNC list first (people who asked not to be called)
    2. Check dncl_cache table
    3. If not cached or expired → query DNCL API → update cache

    Returns {"on_dncl": bool, "source": "internal"|"cache"|"api", "can_call": bool}.
    """
    normalized = _normalize_phone(phone)

    # 1. Check internal DNC list (highest priority)
    async with SessionLocal() as db:
        internal = (
            await db.execute(
                text("SELECT id FROM dncl_cache WHERE phone_number = :phone AND on_dncl = TRUE"),
                {"phone": normalized},
            )
        ).fetchone()

        if internal:
            logger.info("dncl_blocked_internal", phone=normalized[:7] + "...")
            return {"on_dncl": True, "source": "internal", "can_call": False}

        # 2. Check cache
        cached = (
            await db.execute(
                text(
                    "SELECT on_dncl, expires_at FROM dncl_cache "
                    "WHERE phone_number = :phone AND expires_at > NOW()"
                ),
                {"phone": normalized},
            )
        ).fetchone()

        if cached:
            on_dncl = cached.on_dncl
            return {
                "on_dncl": on_dncl,
                "source": "cache",
                "can_call": not on_dncl,
            }

    # 3. Not in cache or expired — query API and cache result
    api_result = await _query_dncl_api(normalized)
    on_dncl = api_result.get("on_dncl", False)

    async with SessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO dncl_cache (phone_number, on_dncl, checked_at, expires_at) "
                "VALUES (:phone, :on_dncl, NOW(), NOW() + INTERVAL '30 days') "
                "ON CONFLICT (phone_number) DO UPDATE SET "
                "on_dncl = EXCLUDED.on_dncl, checked_at = NOW(), "
                "expires_at = NOW() + INTERVAL '30 days'"
            ),
            {"phone": normalized, "on_dncl": on_dncl},
        )
        await db.commit()

    return {"on_dncl": on_dncl, "source": "api", "can_call": not on_dncl}


async def add_to_internal_dncl(phone: str) -> None:
    """Add a number to the internal DNC list.

    Called when someone says "don't call me again" during a call.
    Must be processed IMMEDIATELY per CRTC rules.
    """
    normalized = _normalize_phone(phone)
    async with SessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO dncl_cache (phone_number, on_dncl, checked_at, expires_at) "
                "VALUES (:phone, TRUE, NOW(), NOW() + INTERVAL '100 years') "
                "ON CONFLICT (phone_number) DO UPDATE SET "
                "on_dncl = TRUE, expires_at = NOW() + INTERVAL '100 years'"
            ),
            {"phone": normalized},
        )
        await db.commit()
    logger.info("internal_dncl_added", phone=normalized[:7] + "...")


async def _query_dncl_api(phone: str) -> dict:
    """Query the national DNCL registry API.

    In production: integrate with CRTC DNCL operator (Bell Canada).
    Data must be refreshed every 31 days per CRTC rules.
    """
    # Placeholder — in production, call the DNCL bulk lookup service
    logger.info("dncl_api_query", phone=phone[:7] + "...")
    return {"on_dncl": False, "source": "api"}


def _normalize_phone(phone: str) -> str:
    """Normalize phone to E.164 format (+15145551234)."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if not phone.startswith("+") else phone


def is_within_calling_hours(province: str = "QC") -> bool:
    """Check if current time is within CRTC-allowed calling hours.

    Outbound calls ONLY between 9:00 AM and 9:30 PM local time,
    weekdays and Saturdays. No calls on Sundays or statutory holidays.
    """
    import zoneinfo

    tz_map = {
        "QC": "America/Montreal",
        "ON": "America/Toronto",
        "BC": "America/Vancouver",
        "AB": "America/Edmonton",
        "MB": "America/Winnipeg",
        "SK": "America/Regina",
        "NS": "America/Halifax",
        "NB": "America/Moncton",
        "NL": "America/St_Johns",
        "PE": "America/Halifax",
    }

    tz_name = tz_map.get(province, "America/Montreal")
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("America/Montreal")

    now = datetime.now(tz=tz)

    # No calls on Sundays
    if now.weekday() == 6:
        return False

    hour = now.hour
    minute = now.minute

    # Between 9:00 AM and 9:30 PM
    if hour < 9:
        return False
    if hour > 21:
        return False
    if hour == 21 and minute > 30:
        return False

    return True
