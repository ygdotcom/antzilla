"""Agent 25: Budget Guardian Agent.

Cron hourly. Aggregates costs from agent_logs + budget_tracking for today,
compares to HARD_LIMIT. At >80%: switch Opus→Sonnet→Haiku; at >90%: pause
non-critical agents; reduce voice call volume first. Slack warning at 80%,
critical at 95%.
"""

from __future__ import annotations

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal

logger = structlog.get_logger()

HARD_LIMIT = 50.0
NON_CRITICAL_AGENTS = [
    "content_engine",
    "social_agent",
    "competitor_watch",
    "growth_hacker",
    "self_reflection",
]


async def _send_slack_alert(message: str) -> None:
    if not settings.SLACK_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.SLACK_WEBHOOK_URL, json={"text": message})
    except Exception:
        logger.warning("budget_guardian_slack_failed")


class BudgetGuardianAgent(BaseAgent):
    """Hourly budget check and throttling."""

    agent_name = "budget_guardian"
    default_model = "haiku"

    async def aggregate_costs(self, context) -> dict:
        """Sum from agent_logs + budget_tracking for today."""
        async with SessionLocal() as db:
            agent_total = (
                await db.execute(
                    text(
                        "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                        "FROM agent_logs WHERE created_at > CURRENT_DATE"
                    )
                )
            ).fetchone()
            budget_total = (
                await db.execute(
                    text(
                        "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                        "FROM budget_tracking WHERE date = CURRENT_DATE"
                    )
                )
            ).fetchone()

        agent_spent = float(agent_total.total) if agent_total else 0.0
        budget_spent = float(budget_total.total) if budget_total else 0.0
        total = agent_spent + budget_spent

        return {
            "agent_logs_today": agent_spent,
            "budget_tracking_today": budget_spent,
            "total_today": total,
            "hard_limit": HARD_LIMIT,
            "pct": total / HARD_LIMIT if HARD_LIMIT else 0,
        }

    async def check_limits(self, context) -> dict:
        """Compare to HARD_LIMIT and determine throttle level."""
        data = context.step_output("aggregate_costs")
        total = data["total_today"]
        pct = data["pct"]

        throttle_level = "none"
        if pct >= 0.95:
            throttle_level = "critical"
        elif pct >= 0.90:
            throttle_level = "pause_non_critical"
        elif pct >= 0.80:
            throttle_level = "downgrade_models"

        return {
            "total_today": total,
            "pct": pct,
            "throttle_level": throttle_level,
            "hard_limit": HARD_LIMIT,
        }

    async def throttle_if_needed(self, context) -> dict:
        """If >80%: Opus→Sonnet→Haiku; if >90%: pause non-critical; reduce voice first."""
        data = context.step_output("check_limits")
        throttle = data["throttle_level"]
        total = data["total_today"]
        pct = data["pct"]

        actions_taken = []

        if throttle == "downgrade_models":
            actions_taken.append("Model tier downgrade recommended: Opus→Sonnet→Haiku")
        elif throttle == "pause_non_critical":
            actions_taken.append(f"Pause non-critical agents: {', '.join(NON_CRITICAL_AGENTS)}")
            actions_taken.append("Reduce voice call volume first (most expensive)")
        elif throttle == "critical":
            actions_taken.append("CRITICAL: Pause non-critical agents immediately")
            actions_taken.append("Reduce voice call volume to minimum")

        await self.log_execution(
            action="throttle_if_needed",
            result={
                "throttle_level": throttle,
                "total_today": total,
                "pct": pct,
                "actions": actions_taken,
            },
        )

        return {"throttle_level": throttle, "actions": actions_taken}

    async def alert(self, context) -> dict:
        """Slack warning at 80%, critical at 95%."""
        data = context.step_output("check_limits")
        pct = data["pct"]
        total = data["total_today"]

        if pct >= 0.95:
            await _send_slack_alert(
                f":rotating_light: *Budget CRITICAL* — ${total:.2f}/${HARD_LIMIT:.0f} ({pct:.0%}) today. "
                "Pausing non-critical agents."
            )
        elif pct >= 0.80:
            await _send_slack_alert(
                f":warning: *Budget Warning* — ${total:.2f}/${HARD_LIMIT:.0f} ({pct:.0%}) today. "
                "Consider downgrading model tiers."
            )

        return {"alerted": pct >= 0.80}


def register(hatchet_instance) -> type:
    """Register BudgetGuardianAgent as a Hatchet workflow."""
    from hatchet_sdk import Context

    @hatchet_instance.workflow(name="budget-guardian", on_crons=["0 * * * *"], timeout="5m")
    class _RegisteredBudgetGuardian(BudgetGuardianAgent):
        @hatchet_instance.step(timeout="1m", retries=2)
        async def aggregate_costs(self, context: Context) -> dict:
            return await BudgetGuardianAgent.aggregate_costs(self, context)

        @hatchet_instance.step(timeout="1m", retries=1, parents=["aggregate_costs"])
        async def check_limits(self, context: Context) -> dict:
            return await BudgetGuardianAgent.check_limits(self, context)

        @hatchet_instance.step(timeout="1m", retries=1, parents=["check_limits"])
        async def throttle_if_needed(self, context: Context) -> dict:
            return await BudgetGuardianAgent.throttle_if_needed(self, context)

        @hatchet_instance.step(timeout="1m", retries=1, parents=["throttle_if_needed"])
        async def alert(self, context: Context) -> dict:
            return await BudgetGuardianAgent.alert(self, context)

    return _RegisteredBudgetGuardian
