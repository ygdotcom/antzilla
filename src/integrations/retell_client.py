"""Retell AI client — voice agent creation and outbound call initiation.

$0.07/min all-in.  Handles STT → LLM → TTS in real-time.
"""

from __future__ import annotations

import structlog
import httpx

from src.config import settings

logger = structlog.get_logger()

_BASE = "https://api.retellai.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.RETELL_API_KEY}",
        "Content-Type": "application/json",
    }


async def create_call(
    *,
    agent_id: str,
    phone_number: str,
    from_number: str,
    metadata: dict | None = None,
) -> dict:
    """Initiate an outbound call via Retell AI.

    Returns {"call_id": str, "status": str} or error dict.
    """
    if not settings.RETELL_API_KEY:
        return {"call_id": None, "status": "skipped", "reason": "no API key"}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            payload = {
                "agent_id": agent_id,
                "customer_number": phone_number,
                "from_number": from_number,
            }
            if metadata:
                payload["metadata"] = metadata

            resp = await client.post(
                f"{_BASE}/v2/create-phone-call",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            call_id = data.get("call_id", "")
            logger.info("retell_call_created", call_id=call_id, to=phone_number[:7] + "...")
            return {"call_id": call_id, "status": "initiated"}
        except Exception as exc:
            logger.error("retell_call_failed", error=str(exc))
            return {"call_id": None, "status": "error", "error": str(exc)}


async def get_call(call_id: str) -> dict:
    """Get call details including transcript and analysis."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{_BASE}/v2/get-call/{call_id}", headers=_headers())
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"error": str(exc)}


async def create_agent(
    *,
    name: str,
    system_prompt: str,
    greeting: str,
    language: str = "fr",
    max_duration_seconds: int = 120,
) -> dict:
    """Create or update a Retell voice agent."""
    if not settings.RETELL_API_KEY:
        return {"agent_id": None, "status": "skipped"}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{_BASE}/v2/create-agent",
                headers=_headers(),
                json={
                    "agent_name": name,
                    "response_engine": {
                        "type": "retell-llm",
                        "llm_id": "",
                    },
                    "voice_id": "",
                    "language": language,
                    "general_prompt": system_prompt,
                    "begin_message": greeting,
                    "max_call_duration_ms": max_duration_seconds * 1000,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"agent_id": data.get("agent_id", ""), "status": "created"}
        except Exception as exc:
            return {"agent_id": None, "status": "error", "error": str(exc)}
