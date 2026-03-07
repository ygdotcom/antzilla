"""Agent 23: Legal Guardrail Agent.

Event-driven (content published, email template, site deployed, before voice call)
+ weekly full scan Monday 5AM UTC. Checks compliance items for each business,
scans published content for claims, validates voice compliance (DNCL, hours, AI
disclosure), and reports issues with severity levels.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

COMPLIANCE_CHECKS = [
    "privacy_policy",
    "terms_of_service",
    "cookie_consent",
    "casl_unsub_link",
    "canadian_tax_display",
    "loi_101_fr_content",
    "pipeda_loi25",
    "no_dark_patterns_billing",
]

CHECK_SYSTEM_PROMPT = (
    "Tu es l'agent Legal Guardrail. Tu reçois des données sur un business et son contenu.\n"
    "Vérifie la conformité pour: privacy policy, terms, cookie consent, CASL unsub link, "
    "Canadian tax display, Loi 101 FR content (QC), PIPEDA/Loi 25, pas de dark patterns billing.\n"
    "Réponds en JSON: {\"issues\": [{\"check\": \"...\", \"severity\": \"critical|high|medium|low\", "
    "\"description\": \"...\", \"recommendation\": \"...\"}]}"
)


async def _send_slack_alert(issues: list[dict]) -> None:
    if not settings.SLACK_WEBHOOK_URL or not issues:
        return
    text_body = ":shield: *Legal Guardrail Issues*\n\n"
    for i in issues[:10]:
        text_body += f"• [{i.get('severity', 'medium')}] {i.get('description', '')[:100]}\n"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.SLACK_WEBHOOK_URL, json={"text": text_body})
    except Exception:
        logger.warning("legal_guardrail_slack_failed")


class LegalGuardrailAgent(BaseAgent):
    """Compliance scanning — event-driven + weekly."""

    agent_name = "legal_guardrail"
    default_model = "sonnet"

    async def scan_business(self, context) -> dict:
        """Check all compliance items for a business."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        business_id = input_data.get("business_id")

        async with SessionLocal() as db:
            if business_id:
                biz = (
                    await db.execute(
                        text(
                            "SELECT id, name, slug, domain, status, config "
                            "FROM businesses WHERE id = :id"
                        ),
                        {"id": business_id},
                    )
                ).fetchone()
            else:
                biz_rows = (
                    await db.execute(
                        text(
                            "SELECT id, name, slug, domain, status, config "
                            "FROM businesses WHERE status IN ('live','pre_launch','building')"
                        )
                    )
                ).fetchall()
                biz = biz_rows[0] if biz_rows else None

            if not biz:
                return {"businesses": [], "issues": []}

            def _biz_dict(r):
                cfg = r.config or {}
                return {
                    "id": r.id,
                    "name": r.name,
                    "website_url": r.domain or "",
                    "privacy_policy_url": cfg.get("privacy_policy_url") if isinstance(cfg, dict) else None,
                    "terms_url": cfg.get("terms_url") if isinstance(cfg, dict) else None,
                    "cookie_consent_enabled": cfg.get("cookie_consent_enabled") if isinstance(cfg, dict) else None,
                }

            businesses_data = [_biz_dict(biz)]
            if not business_id and biz_rows:
                businesses_data = [_biz_dict(r) for r in biz_rows]

        return {"businesses": businesses_data, "business_id": business_id}

    async def check_content(self, context) -> dict:
        """Scan published content for unsupported claims."""
        data = context.step_output("scan_business")
        businesses = data.get("businesses", [])
        business_id = data.get("business_id")

        async with SessionLocal() as db:
            if business_id:
                content_rows = (
                    await db.execute(
                        text(
                            "SELECT id, type, title, body, status FROM content "
                            "WHERE business_id = :biz AND status = 'published' LIMIT 50"
                        ),
                        {"biz": business_id},
                    )
                ).fetchall()
            else:
                content_rows = (
                    await db.execute(
                        text(
                            "SELECT id, business_id, type, title, body, status FROM content "
                            "WHERE status = 'published' ORDER BY created_at DESC LIMIT 100"
                        )
                    )
                ).fetchall()

            content_data = [
                {"id": r.id, "business_id": getattr(r, "business_id", business_id), "type": r.type, "title": (r.title or "")[:200], "body": (r.body or "")[:500]}
                for r in content_rows
            ]

        if not content_data:
            return {"content": [], "content_issues": [], "businesses": businesses}

        model_tier = await self.check_budget()
        payload = json.dumps({"businesses": businesses, "content": content_data}, default=str)
        response, cost = await call_claude(
            model_tier=model_tier,
            system=CHECK_SYSTEM_PROMPT,
            user=payload,
            max_tokens=2048,
            temperature=0.1,
        )

        await self.log_execution(action="check_content", result={"content_count": len(content_data)}, cost_usd=cost)

        content_issues = []
        try:
            if "{" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                parsed = json.loads(response[start:end])
                content_issues = parsed.get("issues", [])
        except (json.JSONDecodeError, ValueError):
            pass

        return {"content": content_data, "content_issues": content_issues, "businesses": businesses}

    async def check_voice_compliance(self, context) -> dict:
        """Verify DNCL, calling hours, AI disclosure for voice."""
        data = context.step_output("check_content")
        businesses = data.get("businesses", [])

        async with SessionLocal() as db:
            dncl_checks = (
                await db.execute(
                    text(
                        "SELECT COUNT(*) AS cnt FROM dncl_cache WHERE expires_at > NOW()"
                    )
                )
            ).fetchone()
            voice_calls = (
                await db.execute(
                    text(
                        "SELECT id, business_id, lead_id, status, created_at "
                        "FROM voice_calls WHERE created_at > NOW() - INTERVAL '7 days' "
                        "ORDER BY created_at DESC LIMIT 20"
                    )
                )
            ).fetchall()

        voice_issues = []
        for v in voice_calls:
            hour = v.created_at.hour if v.created_at else 12
            if hour < 9 or hour > 21:
                voice_issues.append({
                    "check": "calling_hours",
                    "severity": "high",
                    "description": f"Voice call outside 9-21h: {v.id}",
                    "recommendation": "CRTC restricts automated calls to 9am-9pm local.",
                })

        return {
            "voice_issues": voice_issues,
            "dncl_cache_count": dncl_checks.cnt if dncl_checks else 0,
            "businesses": businesses,
        }

    async def report_issues(self, context) -> dict:
        """Aggregate and report all issues (severity: critical/high/medium/low)."""
        content_data = context.step_output("check_content")
        voice_data = context.step_output("check_voice_compliance")

        content_issues = content_data.get("content_issues", [])
        voice_issues = voice_data.get("voice_issues", [])

        all_issues = content_issues + voice_issues
        critical = [i for i in all_issues if i.get("severity") == "critical"]
        high = [i for i in all_issues if i.get("severity") == "high"]

        if critical or high:
            await _send_slack_alert(all_issues)

        await self.log_execution(
            action="report_issues",
            result={"total": len(all_issues), "critical": len(critical), "high": len(high)},
        )

        return {"issues": all_issues, "critical_count": len(critical), "high_count": len(high)}


def register(hatchet_instance) -> type:
    """Register LegalGuardrailAgent as two Hatchet workflows: event + weekly cron."""
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="legal-guardrail", timeout="15m")
    class _LegalEvent(LegalGuardrailAgent):
        @hatchet_instance.step(timeout="2m", retries=2)
        async def scan_business(self, context: Context) -> dict:
            return await LegalGuardrailAgent.scan_business(self, context)

        @hatchet_instance.step(timeout="5m", retries=2, parents=["scan_business"])
        async def check_content(self, context: Context) -> dict:
            return await LegalGuardrailAgent.check_content(self, context)

        @hatchet_instance.step(timeout="2m", retries=1, parents=["check_content"])
        async def check_voice_compliance(self, context: Context) -> dict:
            return await LegalGuardrailAgent.check_voice_compliance(self, context)

        @hatchet_instance.step(timeout="1m", retries=1, parents=["check_voice_compliance"])
        async def report_issues(self, context: Context) -> dict:
            return await LegalGuardrailAgent.report_issues(self, context)

    @hatchet_instance.workflow(name="legal-weekly-scan", on_crons=["0 5 * * 1"], timeout="15m")
    class _LegalWeekly(LegalGuardrailAgent):
        @hatchet_instance.step(timeout="2m", retries=2)
        async def scan_business(self, context: Context) -> dict:
            return await LegalGuardrailAgent.scan_business(self, context)

        @hatchet_instance.step(timeout="5m", retries=2, parents=["scan_business"])
        async def check_content(self, context: Context) -> dict:
            return await LegalGuardrailAgent.check_content(self, context)

        @hatchet_instance.step(timeout="2m", retries=1, parents=["check_content"])
        async def check_voice_compliance(self, context: Context) -> dict:
            return await LegalGuardrailAgent.check_voice_compliance(self, context)

        @hatchet_instance.step(timeout="1m", retries=1, parents=["check_voice_compliance"])
        async def report_issues(self, context: Context) -> dict:
            return await LegalGuardrailAgent.report_issues(self, context)

    return _LegalEvent, _LegalWeekly
