"""ZeroBounce API client — email verification.

Verifies emails before outreach. Per spec: reject catch-alls and invalids.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_VALIDATE_URL = "https://api.zerobounce.net/v2/validate"
_BATCH_URL = "https://bulkapi.zerobounce.net/v2/validatebatch"


def _is_deliverable(result: dict) -> bool:
    """Return True if email is deliverable (valid). Reject catch-all and invalid per spec."""
    status = (result.get("status") or "").lower()
    return status == "valid"


async def verify_email(email: str) -> dict:
    """Verify a single email.

    Returns {"email", "status", "sub_status", "did_you_mean"}.
    Status: valid | invalid | catch-all | unknown.
    """
    if not settings.ZEROBOUNCE_API_KEY:
        logger.warning("zerobounce_api_key_not_configured", msg="ZEROBOUNCE_API_KEY not set")
        return {"email": email, "status": "unknown", "sub_status": "", "did_you_mean": ""}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                _VALIDATE_URL,
                params={"api_key": settings.ZEROBOUNCE_API_KEY, "email": email},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "email": data.get("email", email),
                "status": data.get("status", "unknown"),
                "sub_status": data.get("sub_status", ""),
                "did_you_mean": data.get("did_you_mean", ""),
            }
        except Exception as exc:
            logger.error("zerobounce_verify_failed", email=email, error=str(exc))
            return {"email": email, "status": "unknown", "sub_status": str(exc), "did_you_mean": ""}


async def verify_batch(emails: list[str]) -> list[dict]:
    """Verify up to 100 emails per call. Returns list of verification results."""
    if not settings.ZEROBOUNCE_API_KEY:
        logger.warning("zerobounce_api_key_not_configured", msg="ZEROBOUNCE_API_KEY not set")
        return [{"email": e, "status": "unknown", "sub_status": "", "did_you_mean": ""} for e in emails]

    results = []
    for chunk in [emails[i : i + 100] for i in range(0, len(emails), 100)]:
        async with httpx.AsyncClient(timeout=70) as client:
            try:
                payload = {
                    "api_key": settings.ZEROBOUNCE_API_KEY,
                    "email_batch": [{"email_address": e} for e in chunk],
                }
                resp = await client.post(_BATCH_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
                for r in data.get("email_batch", []):
                    results.append({
                        "email": r.get("email", ""),
                        "status": r.get("status", "unknown"),
                        "sub_status": r.get("sub_status", ""),
                        "did_you_mean": r.get("did_you_mean", ""),
                    })
            except Exception as exc:
                logger.error("zerobounce_batch_failed", chunk_size=len(chunk), error=str(exc))
                for e in chunk:
                    results.append({"email": e, "status": "unknown", "sub_status": str(exc), "did_you_mean": ""})
    return results
