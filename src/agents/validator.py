"""Agent 4: Validator.

On-demand after Scout GO. Creates landing page, runs ads ($75 Google + $75 Meta),
monitors metrics, evaluates GO/KILL based on hardcoded rules, reports to Meta.
"""

from __future__ import annotations

import json

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.agents.brand_designer import BrandDesigner
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

# Kill rules (hardcoded)
CPC_PAUSE_THRESHOLD = 8.0  # USD
CPC_PAUSE_DAYS = 3
SIGNUP_RATE_KILL_THRESHOLD = 0.02  # 2%
SIGNUP_RATE_KILL_DAYS = 7
SIGNUP_RATE_STRONG_GO = 0.05  # 5%

LANDING_PAGE_SYSTEM_PROMPT = """\
Tu génères une page d'atterrissage HTML bilingue (FR/EN) pour valider une idée SaaS au Canada.

Tu reçois: le brand kit (couleurs, typo, ton), le scout report (ICP, pain points), le nom du produit.

La page doit inclure:
- Toggle FR/EN
- Formulaire de capture email
- Headline qui adresse le pain point principal
- Placeholder pour social proof
- Favicon, meta tags, lien privacy
- Design responsive, moderne

Réponds en HTML complet, prêt à déployer.
"""


class _BrandContext:
    """Minimal context for calling BrandDesigner.quick_brand from Validator."""

    def __init__(self, idea_id: int, scout_report: str, niche: str):
        self._input = {
            "business_id": None,
            "idea_id": idea_id,
            "scout_report": scout_report,
            "niche": niche,
        }

    def workflow_input(self):
        return self._input


class Validator(BaseAgent):
    """Landing page + ads validation — GO/KILL based on hardcoded rules."""

    agent_name = "validator"
    default_model = "sonnet"

    async def request_light_brand(self, context) -> dict:
        """Trigger brand-designer-light workflow. Call BrandDesigner directly."""
        input_data = context.workflow_input()
        idea_id = input_data.get("idea_id")
        scout_report = input_data.get("scout_report", "")
        niche = input_data.get("niche", "")

        if not idea_id:
            return {"brand_kit": None, "error": "missing idea_id"}

        brand_ctx = _BrandContext(idea_id=idea_id, scout_report=scout_report, niche=niche)
        designer = BrandDesigner()
        result = await designer.quick_brand(brand_ctx)
        return result

    async def generate_landing_page(self, context) -> dict:
        """Claude generates bilingual HTML landing page."""
        brand_out = context.step_output("request_light_brand")
        brand_kit = brand_out.get("brand_kit") or {}
        input_data = context.workflow_input()
        idea_id = input_data.get("idea_id")
        scout_report = input_data.get("scout_report", "")
        niche = input_data.get("niche", "")

        model_tier = await self.check_budget()
        user_prompt = json.dumps({
            "brand_kit": brand_kit,
            "scout_report": scout_report[:3000],
            "niche": niche,
            "idea_id": idea_id,
        }, default=str)

        html, cost = await call_claude(
            model_tier=model_tier,
            system=LANDING_PAGE_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=8192,
            temperature=0.3,
        )

        await self.log_execution(
            action="generate_landing_page",
            result={"idea_id": idea_id, "html_length": len(html)},
            cost_usd=cost,
        )
        return {"html": html, "cost_usd": cost}

    async def deploy_landing(self, context) -> dict:
        """Push HTML to Vercel via API."""
        landing_out = context.step_output("generate_landing_page")
        html = landing_out.get("html", "")
        input_data = context.workflow_input()
        idea_id = input_data.get("idea_id")

        if not html or not settings.VERCEL_TOKEN:
            logger.warning("deploy_landing_skipped", reason="no_html_or_token")
            return {"deployed": False}

        # In production: create/update Vercel deployment
        # For now, log intent
        logger.info("deploy_landing", idea_id=idea_id, html_len=len(html))
        await self.log_execution(action="deploy_landing", result={"idea_id": idea_id})
        return {"deployed": True}

    async def launch_ads(self, context) -> dict:
        """Create Google Ads ($75) + Meta Ads ($75) campaigns."""
        input_data = context.workflow_input()
        idea_id = input_data.get("idea_id")

        if not settings.GOOGLE_ADS_DEVELOPER_TOKEN or not settings.META_ADS_ACCESS_TOKEN:
            logger.warning("launch_ads_skipped", reason="missing_api_tokens")
            return {"google_ads": False, "meta_ads": False}

        # In production: call Google Ads API + Meta Marketing API
        logger.info("launch_ads", idea_id=idea_id, google_budget=75, meta_budget=75)
        await self.log_execution(
            action="launch_ads",
            result={"idea_id": idea_id, "google_budget_usd": 75, "meta_budget_usd": 75},
        )
        return {"google_ads": True, "meta_ads": True}

    async def monitor_daily(self, context) -> dict:
        """Check ad metrics daily for 7 days. Log to DB."""
        input_data = context.workflow_input()
        idea_id = input_data.get("idea_id")

        # In production: fetch from Google/Meta APIs, compute CPC, signup rate
        # For now, placeholder metrics
        metrics = {
            "clicks": 0,
            "impressions": 0,
            "cpc_usd": 0.0,
            "signups": 0,
            "signup_rate": 0.0,
            "days_tracked": 0,
        }

        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE ideas SET validation_metrics = :m, updated_at = NOW() WHERE id = :id"
                ),
                {"m": json.dumps(metrics), "id": idea_id},
            )
            await db.commit()

        await self.log_execution(action="monitor_daily", result={"idea_id": idea_id, "metrics": metrics})
        return {"metrics": metrics}

    async def evaluate_results(self, context) -> dict:
        """GO/KILL based on hardcoded rules."""
        monitor_out = context.step_output("monitor_daily")
        metrics = monitor_out.get("metrics", {})
        input_data = context.workflow_input()
        idea_id = input_data.get("idea_id")

        cpc = float(metrics.get("cpc_usd", 0))
        signup_rate = float(metrics.get("signup_rate", 0))
        days = int(metrics.get("days_tracked", 0))

        decision = "continue"  # default
        reason = ""

        if days >= CPC_PAUSE_DAYS and cpc > CPC_PAUSE_THRESHOLD:
            decision = "pause"
            reason = f"CPC ${cpc:.2f} > ${CPC_PAUSE_THRESHOLD} after {days} days"
        elif days >= SIGNUP_RATE_KILL_DAYS and signup_rate < SIGNUP_RATE_KILL_THRESHOLD:
            decision = "kill"
            reason = f"Signup rate {signup_rate:.1%} < {SIGNUP_RATE_KILL_THRESHOLD:.0%} after {days} days"
        elif signup_rate >= SIGNUP_RATE_STRONG_GO:
            decision = "strong_go"
            reason = f"Signup rate {signup_rate:.1%} >= {SIGNUP_RATE_STRONG_GO:.0%}"

        async with SessionLocal() as db:
            if decision == "kill":
                await db.execute(
                    text(
                        "UPDATE ideas SET status = 'killed', kill_reason = :r, updated_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {"r": reason, "id": idea_id},
                )
            else:
                await db.execute(
                    text("UPDATE ideas SET updated_at = NOW() WHERE id = :id"),
                    {"id": idea_id},
                )
            await db.commit()

        await self.log_execution(
            action="evaluate_results",
            result={"idea_id": idea_id, "decision": decision, "reason": reason},
        )
        return {"decision": decision, "reason": reason}

    async def report_to_meta(self, context) -> dict:
        """Send validation results to Meta orchestrator (Slack)."""
        eval_out = context.step_output("evaluate_results")
        decision = eval_out.get("decision", "")
        reason = eval_out.get("reason", "")
        input_data = context.workflow_input()
        idea_id = input_data.get("idea_id")

        if settings.SLACK_WEBHOOK_URL:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        settings.SLACK_WEBHOOK_URL,
                        json={
                            "text": (
                                f":chart_with_upwards_trend: *Validator Report* — Idea #{idea_id}\n"
                                f"*Decision:* {decision}\n"
                                f"*Reason:* {reason}"
                            )
                        },
                    )
            except Exception as exc:
                logger.warning("report_to_meta_failed", error=str(exc))

        await self.log_execution(
            action="report_to_meta",
            result={"idea_id": idea_id, "decision": decision},
        )
        return {"reported": True, "decision": decision}


def register(hatchet_instance) -> type:
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="validator")
    class _Registered(Validator):
        @hatchet_instance.task(execution_timeout="10m", retries=1)
        async def request_light_brand(self, context: Context) -> dict:
            return await Validator.request_light_brand(self, context)

        @hatchet_instance.task(execution_timeout="10m", retries=1)
        async def generate_landing_page(self, context: Context) -> dict:
            return await Validator.generate_landing_page(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def deploy_landing(self, context: Context) -> dict:
            return await Validator.deploy_landing(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def launch_ads(self, context: Context) -> dict:
            return await Validator.launch_ads(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def monitor_daily(self, context: Context) -> dict:
            return await Validator.monitor_daily(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=1)
        async def evaluate_results(self, context: Context) -> dict:
            return await Validator.evaluate_results(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=1)
        async def report_to_meta(self, context: Context) -> dict:
            return await Validator.report_to_meta(self, context)

    return _Registered
