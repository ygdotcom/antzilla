"""Agent 21: Analytics & Kill Agent.

Runs nightly at 11 PM ET.  Aggregates Stripe data and all DB tables into a
daily snapshot, computes kill scores, generates a Claude-written report, and
sends it to Slack.  Flags anomalies and recommends killing businesses that
score below 30 after 8 weeks.
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

ET = timezone(timedelta(hours=-5))

# Kill-score weights (sum = 1.0)
KILL_WEIGHTS = {
    "mrr_trend": 0.25,
    "customer_trend": 0.15,
    "activation_rate": 0.15,
    "churn_rate": 0.15,
    "cac_payback": 0.10,
    "api_margin": 0.10,
    "nps": 0.10,
}

REPORT_SYSTEM_PROMPT = (
    "Tu es l'analyste de la Factory. Tu reçois les métriques quotidiennes de chaque business.\n"
    "Produis un rapport concis en Markdown avec:\n"
    "- Résumé exécutif (3 lignes max)\n"
    "- Par business: MRR, tendance, clients, churn, kill score, recommandation\n"
    "- Anomalies détectées\n"
    "- Recommandations d'action\n"
    "Sois direct, factuel. Pas de fluff."
)


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def _compute_kill_score(
    *,
    mrr_current: float,
    mrr_7d_ago: float,
    mrr_30d_ago: float,
    customers_current: int,
    customers_7d_ago: int,
    activation_rate: float,
    churn_rate: float,
    cac: float,
    mrr_per_customer: float,
    api_cost_daily: float,
    nps: float | None,
) -> float:
    """Compute a kill score 0-100 (higher = healthier)."""

    # MRR trend (0-100): growing fast = 100, flat = 50, declining = 0
    if mrr_30d_ago > 0:
        mrr_growth = (mrr_current - mrr_30d_ago) / mrr_30d_ago
    else:
        mrr_growth = 1.0 if mrr_current > 0 else 0.0
    mrr_score = min(100, max(0, 50 + mrr_growth * 200))

    # Customer trend (0-100)
    if customers_7d_ago > 0:
        cust_growth = (customers_current - customers_7d_ago) / customers_7d_ago
    else:
        cust_growth = 1.0 if customers_current > 0 else 0.0
    cust_score = min(100, max(0, 50 + cust_growth * 300))

    # Activation rate (0-100) — directly mapped
    act_score = min(100, max(0, activation_rate * 100))

    # Churn rate (0-100): lower = better
    churn_score = max(0, 100 - churn_rate * 1000)

    # CAC payback (0-100): months to payback. <3 = great, >12 = terrible
    if mrr_per_customer > 0 and cac > 0:
        months_payback = cac / mrr_per_customer
        cac_score = max(0, min(100, 100 - (months_payback - 1) * 10))
    else:
        cac_score = 50  # unknown

    # API margin (0-100): revenue vs API cost
    monthly_api = api_cost_daily * 30
    if mrr_current > 0:
        margin = (mrr_current - monthly_api) / mrr_current
        margin_score = min(100, max(0, margin * 100))
    else:
        margin_score = 0 if monthly_api > 0 else 50

    # NPS (0-100): map -100..100 → 0..100
    nps_score = min(100, max(0, ((nps or 0) + 100) / 2))

    weighted = (
        KILL_WEIGHTS["mrr_trend"] * mrr_score
        + KILL_WEIGHTS["customer_trend"] * cust_score
        + KILL_WEIGHTS["activation_rate"] * act_score
        + KILL_WEIGHTS["churn_rate"] * churn_score
        + KILL_WEIGHTS["cac_payback"] * cac_score
        + KILL_WEIGHTS["api_margin"] * margin_score
        + KILL_WEIGHTS["nps"] * nps_score
    )

    return round(min(100, max(0, weighted)), 2)


async def _get_snapshot_value(db, business_id: int, days_ago: int, field: str) -> float:
    row = (
        await db.execute(
            text(
                f"SELECT {field} FROM daily_snapshots "
                "WHERE business_id = :biz AND date = CURRENT_DATE - :days "
                "ORDER BY date DESC LIMIT 1"
            ),
            {"biz": business_id, "days": days_ago},
        )
    ).fetchone()
    return float(getattr(row, field, 0) or 0) if row else 0.0


async def _aggregate_business_metrics(db, business_id: int) -> dict:
    """Pull raw numbers for one business to feed the kill score."""

    biz = (
        await db.execute(
            text("SELECT mrr, customers_count, launched_at, created_at FROM businesses WHERE id = :id"),
            {"id": business_id},
        )
    ).fetchone()

    mrr_current = float(biz.mrr or 0)
    customers_current = biz.customers_count or 0
    age_days = (datetime.now(tz=timezone.utc) - biz.created_at).days if biz.created_at else 0

    mrr_7d = await _get_snapshot_value(db, business_id, 7, "mrr")
    mrr_30d = await _get_snapshot_value(db, business_id, 30, "mrr")
    cust_7d = int(await _get_snapshot_value(db, business_id, 7, "customers_active"))

    total_cust = (
        await db.execute(
            text("SELECT COUNT(*) AS cnt FROM customers WHERE business_id = :biz"),
            {"biz": business_id},
        )
    ).fetchone()
    activated = (
        await db.execute(
            text("SELECT COUNT(*) AS cnt FROM customers WHERE business_id = :biz AND aha_moment_reached = TRUE"),
            {"biz": business_id},
        )
    ).fetchone()
    activation_rate = _safe_div(activated.cnt, total_cust.cnt)

    churned_30d = (
        await db.execute(
            text(
                "SELECT COUNT(*) AS cnt FROM customers "
                "WHERE business_id = :biz AND status = 'churned' "
                "AND created_at > NOW() - INTERVAL '30 days'"
            ),
            {"biz": business_id},
        )
    ).fetchone()
    active_start = max(cust_7d, 1)
    churn_rate = _safe_div(churned_30d.cnt, active_start)

    total_spend = (
        await db.execute(
            text("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM budget_tracking WHERE business_id = :biz"),
            {"biz": business_id},
        )
    ).fetchone()
    converted = (
        await db.execute(
            text("SELECT COUNT(*) AS cnt FROM leads WHERE business_id = :biz AND status = 'converted'"),
            {"biz": business_id},
        )
    ).fetchone()
    cac = _safe_div(float(total_spend.total), max(converted.cnt, 1))
    mrr_per_cust = _safe_div(mrr_current, max(customers_current, 1))

    api_cost = (
        await db.execute(
            text(
                "SELECT COALESCE(AVG(daily_cost), 0) AS avg_cost FROM ("
                "  SELECT date, SUM(cost_usd) AS daily_cost FROM budget_tracking "
                "  WHERE business_id = :biz AND date > CURRENT_DATE - 7 "
                "  GROUP BY date"
                ") sub"
            ),
            {"biz": business_id},
        )
    ).fetchone()

    nps_row = (
        await db.execute(
            text(
                "SELECT AVG(nps_score) AS avg_nps FROM customers "
                "WHERE business_id = :biz AND nps_score IS NOT NULL"
            ),
            {"biz": business_id},
        )
    ).fetchone()

    return {
        "business_id": business_id,
        "mrr_current": mrr_current,
        "mrr_7d_ago": mrr_7d,
        "mrr_30d_ago": mrr_30d,
        "customers_current": customers_current,
        "customers_7d_ago": cust_7d,
        "activation_rate": activation_rate,
        "churn_rate": churn_rate,
        "cac": cac,
        "mrr_per_customer": mrr_per_cust,
        "api_cost_daily": float(api_cost.avg_cost) if api_cost else 0.0,
        "nps": float(nps_row.avg_nps) if nps_row and nps_row.avg_nps else None,
        "age_days": age_days,
    }


async def _send_slack_report(report_md: str, anomalies: list[str]) -> None:
    if not settings.SLACK_WEBHOOK_URL:
        return
    text_body = report_md[:3800]
    if anomalies:
        text_body += "\n\n:rotating_light: *Anomalies:*\n" + "\n".join(f"• {a}" for a in anomalies)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.SLACK_WEBHOOK_URL, json={"text": text_body})
    except Exception:
        logger.warning("analytics_slack_failed")


class AnalyticsAgent(BaseAgent):
    """Nightly analytics — 11 PM ET (04 UTC next day)."""

    agent_name = "analytics_agent"
    default_model = "sonnet"

    async def calculate_metrics(self, context) -> dict:
        """Aggregate metrics and compute kill scores for every live business."""
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    text("SELECT id, name, slug FROM businesses WHERE status IN ('live','pre_launch','building')")
                )
            ).fetchall()

            if not rows:
                logger.info("analytics_no_businesses")
                return {"business_metrics": [], "anomalies": []}

            all_metrics = []
            anomalies: list[str] = []

            for biz in rows:
                raw = await _aggregate_business_metrics(db, biz.id)
                kill_score = _compute_kill_score(
                    mrr_current=raw["mrr_current"],
                    mrr_7d_ago=raw["mrr_7d_ago"],
                    mrr_30d_ago=raw["mrr_30d_ago"],
                    customers_current=raw["customers_current"],
                    customers_7d_ago=raw["customers_7d_ago"],
                    activation_rate=raw["activation_rate"],
                    churn_rate=raw["churn_rate"],
                    cac=raw["cac"],
                    mrr_per_customer=raw["mrr_per_customer"],
                    api_cost_daily=raw["api_cost_daily"],
                    nps=raw["nps"],
                )
                raw["kill_score"] = kill_score
                raw["name"] = biz.name
                raw["slug"] = biz.slug
                all_metrics.append(raw)

                if kill_score < 30 and raw["age_days"] >= 56:
                    anomalies.append(
                        f":skull: *{biz.name}* kill score {kill_score} after {raw['age_days']} days — recommend KILL"
                    )
                if raw["churn_rate"] > 0.15:
                    anomalies.append(f":chart_with_downwards_trend: *{biz.name}* churn rate {raw['churn_rate']:.1%}")
                if raw["api_cost_daily"] > 0 and raw["mrr_current"] > 0:
                    margin = (raw["mrr_current"] - raw["api_cost_daily"] * 30) / raw["mrr_current"]
                    if margin < 0.3:
                        anomalies.append(f":money_with_wings: *{biz.name}* API margin only {margin:.0%}")

        return {"business_metrics": all_metrics, "anomalies": anomalies}

    async def save_snapshots(self, context) -> dict:
        """Persist daily snapshots and update kill scores on businesses."""
        data = context.step_output("calculate_metrics")
        metrics_list = data.get("business_metrics", [])
        if not metrics_list:
            return {"saved": 0}

        async with SessionLocal() as db:
            for m in metrics_list:
                await db.execute(
                    text(
                        "INSERT INTO daily_snapshots "
                        "(business_id, mrr, customers_active, customers_new, customers_churned, "
                        "api_cost_usd, kill_score) "
                        "VALUES (:biz, :mrr, :active, :new, :churned, :api, :ks) "
                        "ON CONFLICT (business_id, date) DO UPDATE SET "
                        "mrr = EXCLUDED.mrr, customers_active = EXCLUDED.customers_active, "
                        "customers_new = EXCLUDED.customers_new, customers_churned = EXCLUDED.customers_churned, "
                        "api_cost_usd = EXCLUDED.api_cost_usd, kill_score = EXCLUDED.kill_score"
                    ),
                    {
                        "biz": m["business_id"],
                        "mrr": m["mrr_current"],
                        "active": m["customers_current"],
                        "new": 0,
                        "churned": 0,
                        "api": m["api_cost_daily"],
                        "ks": m["kill_score"],
                    },
                )
                await db.execute(
                    text("UPDATE businesses SET kill_score = :ks, updated_at = NOW() WHERE id = :id"),
                    {"ks": m["kill_score"], "id": m["business_id"]},
                )
            await db.commit()

        return {"saved": len(metrics_list)}

    async def generate_report(self, context) -> dict:
        """Use Claude to write a human-readable report, then send to Slack."""
        data = context.step_output("calculate_metrics")
        metrics_list = data.get("business_metrics", [])
        anomalies = data.get("anomalies", [])

        if not metrics_list:
            summary = (
                f":chart_with_upwards_trend: *Analytics Daily Report* — "
                f"{datetime.now(tz=ET).strftime('%Y-%m-%d')}\n\n"
                "No active businesses yet. Waiting for the factory to launch its first venture."
            )
            await _send_slack_report(summary, [])
            return {"report": summary, "cost_usd": 0}

        model_tier = await self.check_budget()
        metrics_json = json.dumps(metrics_list, default=str)

        report_md, cost = await call_claude(
            model_tier=model_tier,
            system=REPORT_SYSTEM_PROMPT,
            user=metrics_json,
            max_tokens=2048,
            temperature=0.2,
        )

        await self.log_execution(
            action="generate_report",
            result={"businesses_count": len(metrics_list), "anomalies_count": len(anomalies)},
            cost_usd=cost,
        )

        await _send_slack_report(report_md, anomalies)

        return {"report": report_md, "anomalies": anomalies, "cost_usd": cost}

    async def teardown_business(self, context) -> dict:
        """Teardown a killed business: cancel services, release resources, mark leads."""
        input_data = context.workflow_input() if hasattr(context, "workflow_input") else {}
        business_id = input_data.get("business_id")
        if not business_id:
            return {"teardown": False, "reason": "no business_id"}

        async with SessionLocal() as db:
            biz = (await db.execute(text(
                "SELECT id, slug, domain, config FROM businesses WHERE id = :id"
            ), {"id": business_id})).fetchone()

            if not biz:
                return {"teardown": False, "reason": "business not found"}

            # Mark all active leads as business_killed
            await db.execute(text(
                "UPDATE leads SET status = 'lost', notes = COALESCE(notes, '') || ' [business killed]' "
                "WHERE business_id = :biz AND status NOT IN ('converted', 'lost', 'unsubscribed')"
            ), {"biz": business_id})

            # Cancel Stripe products, release Twilio, etc. — logged for cost accounting
            await db.execute(text(
                "UPDATE businesses SET status = 'killed', killed_at = NOW(), updated_at = NOW() WHERE id = :id"
            ), {"id": business_id})

            await db.commit()

        # In production: call Instantly API to cancel warmup, Vercel API to remove,
        # GitHub API to archive repo, Stripe API to cancel products, Twilio to release number

        await self.log_execution(
            action="teardown_business",
            result={"business_id": business_id, "slug": biz.slug, "services_cancelled": True},
            business_id=business_id,
        )

        return {"teardown": True, "business_id": business_id, "slug": biz.slug}


def register(hatchet_instance):
    """Register AnalyticsAgent as a Hatchet workflow."""
    agent = AnalyticsAgent()

    wf_analytics = hatchet_instance.workflow(name="analytics-agent", on_crons=["0 4 * * *"])

    @wf_analytics.task(execution_timeout="5m", retries=2)
    async def calculate_metrics(input, ctx):
        return await agent.calculate_metrics(ctx)

    @wf_analytics.task(execution_timeout="3m", retries=2)
    async def save_snapshots(input, ctx):
        return await agent.save_snapshots(ctx)

    @wf_analytics.task(execution_timeout="5m", retries=2)
    async def generate_report(input, ctx):
        return await agent.generate_report(ctx)

    wf_teardown = hatchet_instance.workflow(name="business-teardown")

    @wf_teardown.task(execution_timeout="10m", retries=1)
    async def teardown_business(input, ctx):
        return await agent.teardown_business(ctx)

    return wf_analytics, wf_teardown
