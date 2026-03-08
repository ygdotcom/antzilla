"""Slack notification helper — rich messages for the Antzilla pipeline.

All agents should use these functions instead of raw webhook posts.
Messages include actionable links to the dashboard.
"""

from __future__ import annotations

import httpx
import structlog

from src.config import settings

logger = structlog.get_logger()

DASHBOARD_URL = "https://hub.antzilla.ca"


async def send(message: str) -> None:
    """Send a plain text Slack message."""
    url = settings.SLACK_WEBHOOK_URL
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"text": message})
    except Exception:
        logger.warning("slack_send_failed")


async def notify_idea_discovered(idea_name: str, score: float, idea_id: int) -> None:
    """New idea scored and saved."""
    await send(
        f":bulb: *New idea discovered:* {idea_name}\n"
        f"Score: *{score:.1f}/10* | "
        f"<{DASHBOARD_URL}/ideas/{idea_id}|View idea>"
    )


async def notify_idea_validated(idea_name: str, idea_id: int, go_nogo: str) -> None:
    """Deep Scout finished research — GO or NOGO."""
    if go_nogo == "go":
        await send(
            f":white_check_mark: *Deep Scout says GO:* {idea_name}\n"
            f"Ready for your approval → <{DASHBOARD_URL}/ideas|Approve now>"
        )
    else:
        await send(
            f":x: *Deep Scout says NO-GO:* {idea_name}\n"
            f"Idea killed automatically."
        )


async def notify_approval_needed(idea_name: str, idea_id: int) -> None:
    """Idea needs CEO approval to proceed to build."""
    await send(
        f":bell: *Approval needed:* {idea_name}\n"
        f"<{DASHBOARD_URL}/ideas|:point_right: Click here to approve>"
    )


async def notify_build_started(business_name: str, business_id: int) -> None:
    """Build pipeline kicked off."""
    await send(
        f":hammer_and_wrench: *Building:* {business_name}\n"
        f"Brand → Architecture → Code → Deploy\n"
        f"<{DASHBOARD_URL}/console|Watch progress>"
    )


async def notify_build_complete(
    business_name: str, github_repo: str, deployment_url: str | None, cost: float
) -> None:
    """Build pipeline finished."""
    links = []
    if github_repo:
        links.append(f"<https://github.com/{github_repo}|GitHub>")
    if deployment_url:
        links.append(f"<https://{deployment_url}|Live site>")
    link_text = " | ".join(links) if links else "No deployment"

    await send(
        f":rocket: *Built & deployed:* {business_name}\n"
        f"{link_text}\n"
        f"Cost: ${cost:.2f}"
    )


async def notify_build_failed(business_name: str, error: str) -> None:
    """Build pipeline failed."""
    await send(
        f":red_circle: *Build failed:* {business_name}\n"
        f"Error: {error[:200]}\n"
        f"<{DASHBOARD_URL}/console|View logs>"
    )


async def notify_pipeline_event(agent: str, action: str, detail: str = "") -> None:
    """Generic pipeline event (for less important updates)."""
    msg = f":gear: *{agent}:* {action}"
    if detail:
        msg += f"\n{detail}"
    await send(msg)
