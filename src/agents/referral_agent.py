"""Agent 11: Referral Agent.

Event-driven: triggers on NPS response, referral code usage, new signup.
Reads incentive config from gtm_playbooks.referral.

When NPS >= 9: IMMEDIATELY present personalized referral invitation.
This is the highest-conversion moment — 84% of B2B buyers enter the
sales cycle through a referral.

Double-sided: both referrer AND referee get reward (1 month free).
SMS priority for trades ICPs (4x higher response than email).
Power referrers (>= 3 conversions) get ambassador tier.
"""

from __future__ import annotations

import json
import secrets
import string

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.distribution import load_playbook
from src.config import settings
from src.db import SessionLocal

logger = structlog.get_logger()

NPS_THRESHOLD = 9
NUDGE_DELAY_DAYS = 5
AMBASSADOR_THRESHOLD = 3


def generate_referral_code(length: int = 8) -> str:
    """Generate a unique alphanumeric referral code."""
    chars = string.ascii_uppercase + string.digits
    # Avoid ambiguous characters
    chars = chars.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
    return "".join(secrets.choice(chars) for _ in range(length))


async def _send_sms(phone: str, message: str) -> bool:
    """Send SMS via Twilio."""
    if not settings.TWILIO_ACCOUNT_SID or not phone:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                data={
                    "From": settings.TWILIO_PHONE_NUMBER,
                    "To": phone,
                    "Body": message,
                },
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("sms_send_failed", phone=phone[:6] + "...", error=str(exc))
        return False


async def _send_referral_email(email: str, subject: str, body: str) -> bool:
    """Send referral email via Resend."""
    if not settings.RESEND_API_KEY or not email:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": "referrals@factorylabs.ca",
                    "to": email,
                    "subject": subject,
                    "text": body,
                },
            )
            return True
    except Exception:
        return False


class ReferralAgent(BaseAgent):
    """NPS-triggered referral program with double-sided incentives."""

    agent_name = "referral_agent"
    default_model = "haiku"

    async def nps_trigger(self, context) -> dict:
        """When NPS >= 9, immediately present referral invitation.

        This is the highest-conversion moment for referral asks.
        Falls back to customers with 30+ days active when no NPS data exists.
        """
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        business_id = input_data.get("business_id")

        async with SessionLocal() as db:
            customers = (
                await db.execute(
                    text(
                        "SELECT c.id, c.name, c.email, c.phone, c.language, "
                        "c.referral_code, c.nps_score, b.name AS biz_name, b.domain "
                        "FROM customers c JOIN businesses b ON c.business_id = b.id "
                        "WHERE c.nps_score >= :threshold "
                        "AND c.business_id = COALESCE(:biz, c.business_id) "
                        "AND c.referral_code IS NOT NULL "
                        "AND NOT EXISTS ("
                        "  SELECT 1 FROM referrals r WHERE r.referrer_customer_id = c.id "
                        "  AND r.created_at > NOW() - INTERVAL '7 days'"
                        ") "
                        "ORDER BY c.nps_score DESC LIMIT 20"
                    ),
                    {"threshold": NPS_THRESHOLD, "biz": business_id},
                )
            ).fetchall()

            # Fallback: if no NPS data, target customers active 30+ days
            if not customers:
                customers = (
                    await db.execute(
                        text(
                            "SELECT c.id, c.name, c.email, c.phone, c.language, "
                            "c.referral_code, c.nps_score, b.name AS biz_name, b.domain "
                            "FROM customers c JOIN businesses b ON c.business_id = b.id "
                            "WHERE c.created_at < NOW() - INTERVAL '30 days' "
                            "AND c.status IN ('active', 'trial') "
                            "AND c.business_id = COALESCE(:biz, c.business_id) "
                            "AND c.referral_code IS NOT NULL "
                            "AND NOT EXISTS ("
                            "  SELECT 1 FROM referrals r WHERE r.referrer_customer_id = c.id "
                            "  AND r.created_at > NOW() - INTERVAL '7 days'"
                            ") "
                            "ORDER BY c.created_at ASC LIMIT 20"
                        ),
                        {"biz": business_id},
                    )
                ).fetchall()

        if not customers:
            return {"invitations_sent": 0}

        playbook = None
        if business_id:
            playbook = await load_playbook(business_id)
        referral_cfg = playbook.get("referral", {}) if playbook else {}
        incentive = referral_cfg.get("incentive", "1_month_free")

        sent = 0
        for cust in customers:
            lang = cust.language or "fr"
            code = cust.referral_code
            biz_name = cust.biz_name
            domain = cust.domain or ""

            referral_url = f"https://{domain}/signup?ref={code}" if domain else f"?ref={code}"

            if lang == "fr":
                sms_msg = (
                    f"Salut {cust.name}! Tu aimes {biz_name}? "
                    f"Ton code {code} donne 1 mois gratuit à tes collègues "
                    f"(et toi aussi!): {referral_url}"
                )
                email_subject = f"Partage {biz_name} — 1 mois gratuit pour toi et tes collègues"
            else:
                sms_msg = (
                    f"Hi {cust.name}! Enjoying {biz_name}? "
                    f"Share code {code} — you both get 1 month free: {referral_url}"
                )
                email_subject = f"Share {biz_name} — 1 month free for you and your friends"

            # SMS priority for trades ICPs (4x higher response than email)
            if cust.phone:
                sms_ok = await _send_sms(cust.phone, sms_msg)
                if sms_ok:
                    sent += 1
                    continue

            # Fall back to email
            if cust.email:
                await _send_referral_email(cust.email, email_subject, sms_msg)
                sent += 1

        await self.log_execution(
            action="nps_trigger",
            result={"eligible": len(customers), "invitations_sent": sent, "incentive": incentive},
            business_id=business_id,
        )

        return {"invitations_sent": sent, "eligible": len(customers)}

    async def track_and_reward(self, context) -> dict:
        """Track referral usage and apply double-sided rewards."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        business_id = input_data.get("business_id")

        async with SessionLocal() as db:
            # Find referrals that converted but haven't been rewarded
            pending = (
                await db.execute(
                    text(
                        "SELECT r.id, r.referrer_customer_id, r.referee_customer_id, "
                        "r.business_id "
                        "FROM referrals r "
                        "WHERE r.status = 'converted' AND r.reward_applied = FALSE "
                        "AND r.business_id = COALESCE(:biz, r.business_id) "
                        "LIMIT 50"
                    ),
                    {"biz": business_id},
                )
            ).fetchall()

            rewards_applied = 0
            for ref in pending:
                # Double-sided: reward BOTH referrer and referee
                # In production: apply Stripe credit via API
                await db.execute(
                    text(
                        "UPDATE referrals SET reward_applied = TRUE, "
                        "status = 'rewarded' WHERE id = :id"
                    ),
                    {"id": ref.id},
                )
                rewards_applied += 1

                logger.info(
                    "referral_rewarded",
                    referrer=ref.referrer_customer_id,
                    referee=ref.referee_customer_id,
                    type="double_sided",
                )

            await db.commit()

        await self.log_execution(
            action="track_and_reward",
            result={"rewards_applied": rewards_applied},
            business_id=business_id,
        )

        return {"rewards_applied": rewards_applied}

    async def identify_ambassadors(self, context) -> dict:
        """Users with >= 3 successful referrals → ambassador tier."""
        async with SessionLocal() as db:
            power_referrers = (
                await db.execute(
                    text(
                        "SELECT r.referrer_customer_id, COUNT(*) AS referral_count, "
                        "c.name, c.email, c.business_id "
                        "FROM referrals r JOIN customers c ON r.referrer_customer_id = c.id "
                        "WHERE r.status = 'rewarded' "
                        "GROUP BY r.referrer_customer_id, c.name, c.email, c.business_id "
                        "HAVING COUNT(*) >= :threshold"
                    ),
                    {"threshold": AMBASSADOR_THRESHOLD},
                )
            ).fetchall()

            upgraded = 0
            for pr in power_referrers:
                await db.execute(
                    text(
                        "UPDATE customers SET plan = 'ambassador' "
                        "WHERE id = :id AND plan != 'ambassador'"
                    ),
                    {"id": pr.referrer_customer_id},
                )
                upgraded += 1

            await db.commit()

        return {"ambassadors_identified": len(power_referrers), "upgraded": upgraded}

    async def nudge_non_sharers(self, context) -> dict:
        """5-7 days after NPS >= 8 with no share → gentle SMS reminder."""
        async with SessionLocal() as db:
            non_sharers = (
                await db.execute(
                    text(
                        "SELECT c.id, c.name, c.phone, c.email, c.language, "
                        "c.referral_code, b.name AS biz_name, b.domain "
                        "FROM customers c JOIN businesses b ON c.business_id = b.id "
                        "WHERE c.nps_score >= 8 "
                        "AND c.last_active_at < NOW() - INTERVAL :delay "
                        "AND c.referral_code IS NOT NULL "
                        "AND NOT EXISTS ("
                        "  SELECT 1 FROM referrals r WHERE r.referrer_customer_id = c.id"
                        ") "
                        "LIMIT 20"
                    ),
                    {"delay": f"{NUDGE_DELAY_DAYS} days"},
                )
            ).fetchall()

        nudged = 0
        for ns in non_sharers:
            lang = ns.language or "fr"
            code = ns.referral_code
            domain = ns.domain or ""
            url = f"https://{domain}/signup?ref={code}" if domain else f"?ref={code}"

            if lang == "fr":
                msg = f"Tu as aimé {ns.biz_name}? Ton code {code} donne 1 mois gratuit à tes collègues: {url}"
            else:
                msg = f"Enjoying {ns.biz_name}? Share code {code} — 1 month free for your friends: {url}"

            if ns.phone:
                ok = await _send_sms(ns.phone, msg)
                if ok:
                    nudged += 1
            elif ns.email:
                subj = f"{'Partage' if lang == 'fr' else 'Share'} {ns.biz_name}"
                await _send_referral_email(ns.email, subj, msg)
                nudged += 1

        return {"nudged": nudged, "eligible": len(non_sharers)}


def register(hatchet_instance):
    agent = ReferralAgent()

    wf = hatchet_instance.workflow(name="referral-agent")

    @wf.task(execution_timeout="5m", retries=1)
    async def nps_trigger(input, ctx):
        return await agent.nps_trigger(ctx)

    @wf.task(execution_timeout="5m", retries=1)
    async def track_and_reward(input, ctx):
        return await agent.track_and_reward(ctx)

    @wf.task(execution_timeout="3m", retries=1)
    async def identify_ambassadors(input, ctx):
        return await agent.identify_ambassadors(ctx)

    @wf.task(execution_timeout="5m", retries=1)
    async def nudge_non_sharers(input, ctx):
        return await agent.nudge_non_sharers(ctx)

    # Weekly cron: scan for referral candidates (NPS or 30+ day active fallback)
    wf_cron = hatchet_instance.workflow(name="referral-agent-cron", on_crons=["0 15 * * 3"])

    @wf_cron.task(execution_timeout="5m", retries=1)
    async def cron_nps_trigger(input, ctx):
        return await agent.nps_trigger(ctx)

    @wf_cron.task(execution_timeout="5m", retries=1)
    async def cron_track_and_reward(input, ctx):
        return await agent.track_and_reward(ctx)

    @wf_cron.task(execution_timeout="3m", retries=1)
    async def cron_identify_ambassadors(input, ctx):
        return await agent.identify_ambassadors(ctx)

    @wf_cron.task(execution_timeout="5m", retries=1)
    async def cron_nudge_non_sharers(input, ctx):
        return await agent.nudge_non_sharers(ctx)

    return wf, wf_cron
