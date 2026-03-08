"""Agent 20: Onboarding Agent.

Event-driven (new signup) + daily stall check.
Two modes: PRE_BUILD (generate onboarding spec for Builder) and OPERATE
(track progress, nudges at 24h/72h, celebrate aha moment, trigger Referral after activation).
"""

from __future__ import annotations

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal

logger = structlog.get_logger()

NUDGE_24H = 24
NUDGE_72H = 72


class OnboardingAgent(BaseAgent):
    """Track onboarding progress, send nudges, trigger referral on aha moment."""

    agent_name = "onboarding_agent"
    default_model = "haiku"

    async def check_new_signups(self, context) -> dict:
        """Customers with onboarding_step=0 (new signups)."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        business_id = input_data.get("business_id")

        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT c.id, c.name, c.email, c.phone, c.language, c.onboarding_step, "
                        "c.created_at, c.aha_moment_reached, b.name AS biz_name "
                        "FROM customers c JOIN businesses b ON c.business_id = b.id "
                        "WHERE c.onboarding_step = 0 "
                        "AND c.aha_moment_reached = FALSE "
                        "AND c.business_id = COALESCE(:biz, c.business_id) "
                        "ORDER BY c.created_at DESC LIMIT 50"
                    ),
                    {"biz": business_id},
                )
            ).fetchall()

        signups = [
            {
                "id": r.id,
                "name": r.name,
                "email": r.email,
                "phone": r.phone,
                "language": r.language or "fr",
                "created_at": str(r.created_at) if r.created_at else None,
                "biz_name": r.biz_name,
            }
            for r in rows
        ]
        return {"signups": signups}

    async def send_nudge(self, context) -> dict:
        """If stalled 24h+, send SMS/email nudge."""
        check_out = context.step_output("check_new_signups")
        signups = check_out.get("signups", [])

        from datetime import datetime, timedelta, timezone

        now = datetime.now(tz=timezone.utc)
        nudged = 0
        for s in signups:
            created = s.get("created_at")
            if not created:
                continue
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                continue
            hours_since = (now - dt).total_seconds() / 3600
            if hours_since < NUDGE_24H:
                continue

            lang = s.get("language", "fr")
            msg_fr = f"Salut {s.get('name', '')}! Tu as commencé ton onboarding sur {s.get('biz_name', '')}. Besoin d'aide?"
            msg_en = f"Hi {s.get('name', '')}! You started onboarding on {s.get('biz_name', '')}. Need help?"
            msg = msg_fr if lang == "fr" else msg_en

            if s.get("phone") and settings.TWILIO_ACCOUNT_SID:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                            data={
                                "From": settings.TWILIO_PHONE_NUMBER,
                                "To": s["phone"],
                                "Body": msg,
                            },
                        )
                    nudged += 1
                except Exception as exc:
                    logger.warning("onboarding_nudge_sms_failed", customer_id=s["id"], error=str(exc))

            elif s.get("email") and settings.RESEND_API_KEY:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            "https://api.resend.com/emails",
                            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                            json={
                                "from": "onboarding@factorylabs.ca",
                                "to": s["email"],
                                "subject": "Besoin d'aide?" if lang == "fr" else "Need help?",
                                "text": msg,
                            },
                        )
                    nudged += 1
                except Exception as exc:
                    logger.warning("onboarding_nudge_email_failed", customer_id=s["id"], error=str(exc))

        return {"nudged": nudged, "eligible": len(signups)}

    async def check_aha_moment(self, context) -> dict:
        """If aha_moment_reached, trigger referral-agent."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        business_id = input_data.get("business_id")

        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT c.id, c.business_id FROM customers c "
                        "WHERE c.aha_moment_reached = TRUE "
                        "AND c.aha_moment_at > NOW() - INTERVAL '7 days' "
                        "AND c.business_id = COALESCE(:biz, c.business_id) "
                        "AND NOT EXISTS ("
                        "  SELECT 1 FROM agent_logs al "
                        "  WHERE al.agent_name = 'onboarding_agent' AND al.action = 'referral_triggered' "
                        "  AND (al.result->>'customer_id')::text = c.id::text "
                        ") "
                        "LIMIT 20"
                    ),
                    {"biz": business_id},
                )
            ).fetchall()

        triggered = 0
        for row in rows:
            logger.info("onboarding_aha_trigger_referral", customer_id=row.id)
            if hasattr(self, "_hatchet_admin") and self._hatchet_admin:
                try:
                    await self._hatchet_admin.run_workflow(
                        "referral-agent", {"business_id": row.business_id, "customer_id": row.id}
                    )
                    triggered += 1
                    await self.log_execution(
                        action="referral_triggered",
                        result={"customer_id": row.id, "business_id": row.business_id},
                        business_id=row.business_id,
                    )
                except Exception as exc:
                    logger.warning("referral_trigger_failed", customer_id=row.id, error=str(exc))

        return {"triggered_referral": triggered > 0, "count": triggered}

    async def track_progress(self, context) -> dict:
        """Log onboarding progress."""
        check_out = context.step_output("check_new_signups")
        nudge_out = context.step_output("send_nudge")
        aha_out = context.step_output("check_aha_moment")

        await self.log_execution(
            action="track_progress",
            result={
                "signups_count": len(check_out.get("signups", [])),
                "nudged": nudge_out.get("nudged", 0),
                "triggered_referral": aha_out.get("triggered_referral", False),
            },
        )
        return {"tracked": True}


class OnboardingStallCheckAgent(OnboardingAgent):
    """Daily cron: check for stalled onboardings and send nudges."""

    async def check_stalled(self, context) -> dict:
        """Find customers stalled 24h+ with onboarding_step=0."""
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT c.id, c.name, c.email, c.phone, c.language, c.created_at, "
                        "b.name AS biz_name, b.slug "
                        "FROM customers c JOIN businesses b ON c.business_id = b.id "
                        "WHERE c.onboarding_step = 0 "
                        "AND c.aha_moment_reached = FALSE "
                        "AND c.created_at < NOW() - INTERVAL '24 hours' "
                        "ORDER BY c.created_at ASC LIMIT 30"
                    )
                )
            ).fetchall()

        stalled = [
            {
                "id": r.id,
                "name": r.name,
                "email": r.email,
                "phone": r.phone,
                "language": r.language or "fr",
                "biz_name": r.biz_name,
            }
            for r in rows
        ]

        nudged = 0
        for s in stalled:
            lang = s.get("language", "fr")
            msg = (
                f"Salut {s.get('name', '')}! Tu as commencé il y a plus de 24h. On peut t'aider?"
                if lang == "fr"
                else f"Hi {s.get('name', '')}! You started over 24h ago. Can we help?"
            )
            if s.get("email") and settings.RESEND_API_KEY:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            "https://api.resend.com/emails",
                            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                            json={
                                "from": "onboarding@factorylabs.ca",
                                "to": s["email"],
                                "subject": "Tu es toujours là?" if lang == "fr" else "Still there?",
                                "text": msg,
                            },
                        )
                    nudged += 1
                except Exception:
                    pass

        await self.log_execution(action="check_stalled", result={"stalled": len(stalled), "nudged": nudged})
        return {"stalled": len(stalled), "nudged": nudged}


def register(hatchet_instance) -> type:

    @hatchet_instance.workflow(name="onboarding-agent")
    class _Registered(OnboardingAgent):
        @hatchet_instance.task(execution_timeout="3m", retries=1)
        async def check_new_signups(self, context) -> dict:
            return await OnboardingAgent.check_new_signups(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def send_nudge(self, context) -> dict:
            return await OnboardingAgent.send_nudge(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=1)
        async def check_aha_moment(self, context) -> dict:
            return await OnboardingAgent.check_aha_moment(self, context)

        @hatchet_instance.task(execution_timeout="1m", retries=1)
        async def track_progress(self, context) -> dict:
            return await OnboardingAgent.track_progress(self, context)

    @hatchet_instance.workflow(name="onboarding-stall-check", on_crons=["0 14 * * *"])
    class _StallCheck(OnboardingStallCheckAgent):
        @hatchet_instance.task(execution_timeout="10m", retries=1)
        async def check_stalled(self, context) -> dict:
            return await OnboardingStallCheckAgent.check_stalled(self, context)

    return _Registered, _StallCheck
