"""Tests for the Analytics & Kill Agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.analytics_agent import (
    AnalyticsAgent,
    _compute_kill_score,
    _send_slack_report,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    return AnalyticsAgent()


# ── Kill Score Unit Tests ─────────────────────────────────────────────────────


class TestComputeKillScore:
    def test_healthy_business_scores_high(self):
        score = _compute_kill_score(
            mrr_current=5000,
            mrr_7d_ago=4500,
            mrr_30d_ago=3000,
            customers_current=50,
            customers_7d_ago=45,
            activation_rate=0.8,
            churn_rate=0.02,
            cac=100,
            mrr_per_customer=100,
            api_cost_daily=5.0,
            nps=60,
        )
        assert score > 70, f"Healthy business should score >70, got {score}"

    def test_dying_business_scores_low(self):
        score = _compute_kill_score(
            mrr_current=50,
            mrr_7d_ago=100,
            mrr_30d_ago=500,
            customers_current=2,
            customers_7d_ago=5,
            activation_rate=0.1,
            churn_rate=0.3,
            cac=500,
            mrr_per_customer=25,
            api_cost_daily=10.0,
            nps=-20,
        )
        assert score < 30, f"Dying business should score <30, got {score}"

    def test_new_business_with_no_data_is_moderate(self):
        score = _compute_kill_score(
            mrr_current=0,
            mrr_7d_ago=0,
            mrr_30d_ago=0,
            customers_current=0,
            customers_7d_ago=0,
            activation_rate=0.0,
            churn_rate=0.0,
            cac=0,
            mrr_per_customer=0,
            api_cost_daily=0,
            nps=None,
        )
        assert 20 <= score <= 60, f"New zero-data business should be moderate, got {score}"

    def test_score_is_bounded_0_100(self):
        high = _compute_kill_score(
            mrr_current=100_000,
            mrr_7d_ago=50_000,
            mrr_30d_ago=10_000,
            customers_current=1000,
            customers_7d_ago=500,
            activation_rate=1.0,
            churn_rate=0.0,
            cac=10,
            mrr_per_customer=100,
            api_cost_daily=0.01,
            nps=100,
        )
        assert 0 <= high <= 100

        low = _compute_kill_score(
            mrr_current=0,
            mrr_7d_ago=10_000,
            mrr_30d_ago=50_000,
            customers_current=0,
            customers_7d_ago=1000,
            activation_rate=0.0,
            churn_rate=1.0,
            cac=10_000,
            mrr_per_customer=0,
            api_cost_daily=100,
            nps=-100,
        )
        assert 0 <= low <= 100

    def test_high_churn_penalized(self):
        base = _compute_kill_score(
            mrr_current=1000, mrr_7d_ago=1000, mrr_30d_ago=1000,
            customers_current=20, customers_7d_ago=20,
            activation_rate=0.5, churn_rate=0.02,
            cac=50, mrr_per_customer=50,
            api_cost_daily=2.0, nps=30,
        )
        high_churn = _compute_kill_score(
            mrr_current=1000, mrr_7d_ago=1000, mrr_30d_ago=1000,
            customers_current=20, customers_7d_ago=20,
            activation_rate=0.5, churn_rate=0.20,
            cac=50, mrr_per_customer=50,
            api_cost_daily=2.0, nps=30,
        )
        assert high_churn < base, "Higher churn should lower the kill score"

    def test_mrr_growth_boosts_score(self):
        flat = _compute_kill_score(
            mrr_current=1000, mrr_7d_ago=1000, mrr_30d_ago=1000,
            customers_current=20, customers_7d_ago=20,
            activation_rate=0.5, churn_rate=0.03,
            cac=50, mrr_per_customer=50,
            api_cost_daily=2.0, nps=30,
        )
        growing = _compute_kill_score(
            mrr_current=2000, mrr_7d_ago=1500, mrr_30d_ago=1000,
            customers_current=20, customers_7d_ago=20,
            activation_rate=0.5, churn_rate=0.03,
            cac=50, mrr_per_customer=100,
            api_cost_daily=2.0, nps=30,
        )
        assert growing > flat, "MRR growth should boost the kill score"

    def test_negative_api_margin_penalized(self):
        profitable = _compute_kill_score(
            mrr_current=1000, mrr_7d_ago=1000, mrr_30d_ago=1000,
            customers_current=10, customers_7d_ago=10,
            activation_rate=0.5, churn_rate=0.03,
            cac=50, mrr_per_customer=100,
            api_cost_daily=1.0, nps=40,
        )
        unprofitable = _compute_kill_score(
            mrr_current=1000, mrr_7d_ago=1000, mrr_30d_ago=1000,
            customers_current=10, customers_7d_ago=10,
            activation_rate=0.5, churn_rate=0.03,
            cac=50, mrr_per_customer=100,
            api_cost_daily=50.0, nps=40,
        )
        assert unprofitable < profitable


class TestAnalyticsAgentConfig:
    def test_agent_name(self, agent):
        assert agent.agent_name == "analytics_agent"

    def test_default_model_is_sonnet(self, agent):
        assert agent.default_model == "sonnet"


class TestCalculateMetrics:
    @pytest.mark.asyncio
    async def test_no_businesses_returns_empty(self, agent):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=[]))
        )

        with patch("src.agents.analytics_agent.SessionLocal", return_value=mock_db):
            ctx = MagicMock(spec=["step_output"])
            result = await agent.calculate_metrics(ctx)

        assert result["business_metrics"] == []
        assert result["anomalies"] == []


class TestSaveSnapshots:
    @pytest.mark.asyncio
    async def test_no_metrics_saves_zero(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={"business_metrics": [], "anomalies": []})
        result = await agent.save_snapshots(ctx)
        assert result["saved"] == 0


class TestGenerateReport:
    @pytest.mark.asyncio
    async def test_empty_report_no_llm_call(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={"business_metrics": [], "anomalies": []})

        with patch("src.agents.analytics_agent._send_slack_report", new_callable=AsyncMock) as mock_slack:
            result = await agent.generate_report(ctx)

        assert result["cost_usd"] == 0
        assert "No active businesses" in result["report"]
        mock_slack.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_with_data_calls_llm(self, agent):
        metrics = [
            {
                "business_id": 1, "name": "TestBiz", "slug": "test",
                "mrr_current": 500, "customers_current": 5,
                "kill_score": 65, "age_days": 30,
                "churn_rate": 0.03, "api_cost_daily": 2.0,
            }
        ]
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            return_value={"business_metrics": metrics, "anomalies": []}
        )

        with (
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="sonnet"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.analytics_agent.call_claude", new_callable=AsyncMock) as mock_claude,
            patch("src.agents.analytics_agent._send_slack_report", new_callable=AsyncMock),
        ):
            mock_claude.return_value = ("# Report\nAll good.", 0.01)
            result = await agent.generate_report(ctx)

        assert result["cost_usd"] == 0.01
        assert "Report" in result["report"]
        mock_claude.assert_called_once()


class TestSlackReport:
    @pytest.mark.asyncio
    async def test_skips_when_no_webhook(self):
        with patch("src.agents.analytics_agent.settings") as mock_settings:
            mock_settings.SLACK_WEBHOOK_URL = ""
            await _send_slack_report("test report", [])

    @pytest.mark.asyncio
    async def test_sends_with_anomalies(self):
        with (
            patch("src.agents.analytics_agent.settings") as mock_settings,
            patch("src.agents.analytics_agent.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock()
            mock_client_cls.return_value = mock_client

            await _send_slack_report("# Report", [":skull: biz1 dying"])
            mock_client.post.assert_called_once()
            call_body = mock_client.post.call_args[1]["json"]["text"]
            assert "Anomalies" in call_body


class TestKillScoreThreshold:
    """Spec says: kill score < 30 after 8 weeks (56 days) = recommend KILL."""

    def test_old_low_score_triggers_kill(self):
        score = _compute_kill_score(
            mrr_current=20, mrr_7d_ago=50, mrr_30d_ago=200,
            customers_current=1, customers_7d_ago=3,
            activation_rate=0.05, churn_rate=0.4,
            cac=300, mrr_per_customer=20,
            api_cost_daily=8.0, nps=-30,
        )
        assert score < 30, f"Expected < 30 for dying business, got {score}"
