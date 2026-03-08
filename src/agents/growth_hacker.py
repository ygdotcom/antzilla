"""Agent 27: Growth Hacker Agent.

Cron weekly Tuesday 6AM UTC + on-demand when business stuck. Researches
non-obvious growth tactics, scores by Impact×Repeatability/(Effort×Cost),
auto-executes easy ones (directories, free tools), proposes complex to Slack,
tracks results after 30 days.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

TACTIC_TYPES = [
    "marketplace_listing",
    "integration_plugin",
    "data_as_marketing",
    "community",
    "event_piggybacking",
    "strategic_partnership",
    "template_bait",
    "competitor_traffic",
    "regulation_piggyback",
    "micro_influencer",
    "government_listing",
    "trigger_outreach",
]

RESEARCH_SYSTEM_PROMPT = (
    "Tu es le Growth Hacker Agent. Ton job est de trouver des méthodes NON-CONVENTIONNELLES "
    "pour acquérir des clients. Tu ne fais PAS: SEO, cold email, social posting, referral, voice.\n"
    "Pour chaque business, propose des tactiques parmi: marketplace_listing, integration_plugin, "
    "data_as_marketing, community, event_piggybacking, strategic_partnership, template_bait, "
    "competitor_traffic, regulation_piggyback, micro_influencer, government_listing, trigger_outreach.\n"
    "Pour chaque tactique: impact (1-10), repeatability (1-10), effort (1-10), cost (1-10). "
    "Score = (impact * repeatability) / (effort * cost). "
    "Réponds en JSON: {\"tactics\": [{\"type\": \"...\", \"description\": \"...\", "
    "\"impact\": N, \"repeatability\": N, \"effort\": N, \"cost\": N, \"score\": N, "
    "\"auto_executable\": bool, \"action\": \"...\"}]}"
)


async def _send_slack_report(message: str) -> None:
    if not settings.SLACK_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.SLACK_WEBHOOK_URL, json={"text": message[:3800]})
    except Exception:
        logger.warning("growth_hacker_slack_failed")


class GrowthHackerAgent(BaseAgent):
    """Weekly growth tactics — Tuesday 6AM UTC."""

    agent_name = "growth_hacker"
    default_model = "opus"

    async def research_opportunities(self, context) -> dict:
        """For each business, use Claude to find non-obvious growth tactics."""
        async with SessionLocal() as db:
            businesses = (
                await db.execute(
                    text(
                        "SELECT id, name, slug, website_url, status, mrr, customers_count "
                        "FROM businesses WHERE status IN ('live','pre_launch','building')"
                    )
                )
            ).fetchall()

        if not businesses:
            return {"businesses": [], "tactics_by_business": {}}

        biz_data = [
            {"id": b.id, "name": b.name, "slug": b.slug, "website_url": b.website_url, "mrr": float(b.mrr or 0), "customers": b.customers_count or 0}
            for b in businesses
        ]

        model_tier = await self.check_budget()
        payload = json.dumps({"businesses": biz_data}, default=str)
        response, cost = await call_claude(
            model_tier=model_tier,
            system=RESEARCH_SYSTEM_PROMPT,
            user=payload,
            max_tokens=4096,
            temperature=0.3,
        )

        await self.log_execution(
            action="research_opportunities",
            result={"business_count": len(businesses)},
            cost_usd=cost,
        )

        tactics_by_business = {}
        try:
            if "{" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                parsed = json.loads(response[start:end])
                for i, biz in enumerate(biz_data):
                    tactics = parsed.get("tactics", [])
                    if isinstance(tactics, list) and tactics:
                        tactics_by_business[biz["id"]] = tactics[:10]
                    else:
                        tactics_by_business[biz["id"]] = []
        except (json.JSONDecodeError, ValueError):
            for b in biz_data:
                tactics_by_business[b["id"]] = []

        return {"businesses": biz_data, "tactics_by_business": tactics_by_business, "cost_usd": cost}

    async def score_and_prioritize(self, context) -> dict:
        """Score: Impact × Repeatability / (Effort × Cost)."""
        data = context.step_output("research_opportunities")
        tactics_by_business = data.get("tactics_by_business", {})

        scored = {}
        for biz_id, tactics in tactics_by_business.items():
            for t in tactics:
                imp = max(1, min(10, float(t.get("impact", 5))))
                rep = max(1, min(10, float(t.get("repeatability", 5))))
                eff = max(1, min(10, float(t.get("effort", 5))))
                cost = max(1, min(10, float(t.get("cost", 5))))
                t["score"] = round((imp * rep) / (eff * cost), 2)
            scored[biz_id] = sorted(tactics, key=lambda x: x.get("score", 0), reverse=True)

        return {"scored_tactics": scored}

    async def auto_execute_easy(self, context) -> dict:
        """Submit to directories, create free tools — placeholder for actual execution."""
        data = context.step_output("score_and_prioritize")
        scored = data.get("scored_tactics", {})

        executed = 0
        for biz_id, tactics in scored.items():
            for t in tactics[:3]:
                if t.get("auto_executable"):
                    executed += 1

        await self.log_execution(
            action="auto_execute_easy",
            result={"executed_count": executed},
        )

        return {"auto_executed": executed}

    async def propose_complex(self, context) -> dict:
        """Slack for human review on complex tactics."""
        data = context.step_output("score_and_prioritize")
        scored = data.get("scored_tactics", {})
        biz_data = context.step_output("research_opportunities").get("businesses", [])

        biz_map = {b["id"]: b["name"] for b in biz_data}
        report = ":rocket: *Growth Hacker Weekly Report*\n\n"

        for biz_id, tactics in scored.items():
            name = biz_map.get(biz_id, "Unknown")
            report += f"*{name}*\n"
            for t in tactics[:5]:
                auto = "✓ auto" if t.get("auto_executable") else "→ review"
                report += f"  • [{t.get('type', '')}] {t.get('description', '')[:80]}... (score: {t.get('score', 0)}) {auto}\n"
            report += "\n"

        await _send_slack_report(report)

        return {"report_sent": True}

    async def track_and_learn(self, context) -> dict:
        """Measure results after 30 days — placeholder for metrics tracking."""
        await self.log_execution(
            action="track_and_learn",
            result={"status": "tracking_enabled"},
        )
        return {"tracking": "30_day_window"}


def register(hatchet_instance) -> type:
    """Register GrowthHackerAgent as a Hatchet workflow."""

    @hatchet_instance.workflow(name="growth-hacker", on_crons=["0 11 * * 2"])
    class _RegisteredGrowthHacker(GrowthHackerAgent):
        @hatchet_instance.task(execution_timeout="15m", retries=2)
        async def research_opportunities(self, context) -> dict:
            return await GrowthHackerAgent.research_opportunities(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=1)
        async def score_and_prioritize(self, context) -> dict:
            return await GrowthHackerAgent.score_and_prioritize(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=1)
        async def auto_execute_easy(self, context) -> dict:
            return await GrowthHackerAgent.auto_execute_easy(self, context)

        @hatchet_instance.task(execution_timeout="2m", retries=1)
        async def propose_complex(self, context) -> dict:
            return await GrowthHackerAgent.propose_complex(self, context)

        @hatchet_instance.task(execution_timeout="1m", retries=1)
        async def track_and_learn(self, context) -> dict:
            return await GrowthHackerAgent.track_and_learn(self, context)

    return _RegisteredGrowthHacker
