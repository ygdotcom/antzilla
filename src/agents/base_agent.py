"""Base class for all factory agents.

Provides:
- Budget circuit breaker (auto-downgrades model tier, hard stops at limit)
- Automatic logging to agent_logs table
- Execution timing
- Slack alerting at 80% budget threshold
"""

from __future__ import annotations

import json
import time

import httpx
import structlog
from sqlalchemy import text

from src.config import settings
from src.db import SessionLocal

logger = structlog.get_logger()


class BudgetExceededError(Exception):
    pass


class BaseAgent:
    agent_name: str = "unknown"
    default_model: str = "sonnet"

    async def check_budget(self) -> str:
        """Check budget and return the model tier to use. Auto-downgrades if approaching limit."""
        async with SessionLocal() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT COALESCE(SUM(cost_usd), 0) AS spent "
                        "FROM agent_logs "
                        "WHERE agent_name = :name AND created_at > CURRENT_DATE"
                    ),
                    {"name": self.agent_name},
                )
            ).fetchone()
            daily_spent = float(row.spent)

            agent_limit = settings.AGENT_DEFAULT_DAILY_LIMIT_USD

            if daily_spent >= agent_limit:
                raise BudgetExceededError(
                    f"{self.agent_name} daily budget exhausted "
                    f"(${daily_spent:.2f}/${agent_limit:.2f})"
                )

            if daily_spent > agent_limit * 0.8:
                await self._alert_budget_warning(daily_spent, agent_limit)
                if self.default_model == "opus":
                    return "sonnet"
                if self.default_model == "sonnet":
                    return "haiku"

            # Global daily limit
            global_row = (
                await db.execute(
                    text(
                        "SELECT COALESCE(SUM(cost_usd), 0) AS spent "
                        "FROM agent_logs WHERE created_at > CURRENT_DATE"
                    )
                )
            ).fetchone()
            if float(global_row.spent) >= settings.DAILY_BUDGET_LIMIT_USD:
                raise BudgetExceededError("Global daily budget exhausted")

            return self.default_model

    async def log_execution(
        self,
        *,
        action: str,
        result: dict | None = None,
        cost_usd: float = 0.0,
        duration_seconds: float = 0.0,
        status: str = "success",
        error_message: str | None = None,
        business_id: int | None = None,
        workflow_run_id: str | None = None,
    ) -> None:
        """Log every execution for the Self-Reflection agent to analyze."""
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO agent_logs "
                    "(agent_name, business_id, workflow_run_id, action, result, cost_usd, "
                    "duration_seconds, status, error_message) "
                    "VALUES (:name, :biz, :run, :action, :result, :cost, :dur, :status, :err)"
                ),
                {
                    "name": self.agent_name,
                    "biz": business_id,
                    "run": workflow_run_id,
                    "action": action,
                    "result": json.dumps(result) if result else None,
                    "cost": cost_usd,
                    "dur": duration_seconds,
                    "status": status,
                    "err": error_message,
                },
            )
            await db.commit()

    async def run_with_tracking(self, action: str, coro, **log_kwargs):
        """Wrap an async operation with timing, logging, and error handling."""
        t0 = time.monotonic()
        try:
            result = await coro
            elapsed = time.monotonic() - t0
            await self.log_execution(
                action=action,
                result=result if isinstance(result, dict) else {"output": str(result)},
                duration_seconds=elapsed,
                **log_kwargs,
            )
            return result
        except BudgetExceededError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("agent_error", agent=self.agent_name, action=action, error=str(exc))
            await self.log_execution(
                action=action,
                status="error",
                error_message=str(exc),
                duration_seconds=elapsed,
                **log_kwargs,
            )
            raise

    async def _alert_budget_warning(self, spent: float, limit: float) -> None:
        """Send a Slack alert when an agent hits 80% of its daily budget."""
        if not settings.SLACK_WEBHOOK_URL:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    settings.SLACK_WEBHOOK_URL,
                    json={
                        "text": (
                            f":warning: *{self.agent_name}* at {spent/limit:.0%} of daily budget "
                            f"(${spent:.2f}/${limit:.2f}). Model auto-downgraded."
                        )
                    },
                )
        except Exception:
            logger.warning("slack_alert_failed", agent=self.agent_name)
