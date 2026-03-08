"""Tests for the Meta Orchestrator agent."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.meta_orchestrator import MetaOrchestrator, _load_prompt, _send_slack_digest


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def orchestrator():
    return MetaOrchestrator()


@pytest.fixture
def empty_metrics():
    return {
        "businesses": [],
        "snapshots": {},
        "errors_24h": [],
        "error_rates_24h": [],
        "pending_improvements": [],
        "budget_yesterday": {"total_usd": 0, "limit_usd": 50.0, "by_agent": {}},
        "lead_pipeline": {},
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@pytest.fixture
def populated_metrics():
    return {
        "businesses": [
            {
                "id": 1,
                "name": "Toîturo",
                "slug": "toituro",
                "status": "live",
                "mrr": 490.0,
                "customers": 10,
                "kill_score": 72.5,
                "launched_at": "2026-01-15T00:00:00+00:00",
                "age_days": 51,
            }
        ],
        "snapshots": {
            1: [
                {"date": "2026-03-06", "mrr": 490, "active": 10, "new": 1, "churned": 0,
                 "leads_new": 5, "leads_converted": 1, "api_cost": 3.2, "kill_score": 72.5},
            ]
        },
        "errors_24h": [
            {"agent": "content_engine", "action": "publish", "error": "timeout", "at": "2026-03-07T02:00:00+00:00"}
        ],
        "error_rates_24h": [
            {"agent": "content_engine", "total": 10, "errors": 1, "error_rate": 0.1}
        ],
        "pending_improvements": [],
        "budget_yesterday": {"total_usd": 12.5, "limit_usd": 50.0, "by_agent": {"content_engine": 5.0}},
        "lead_pipeline": {1: {"new": 15, "contacted": 8, "replied": 3}},
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@pytest.fixture
def valid_decisions():
    return {
        "priorities": ["Increase Toîturo outreach", "Fix content_engine timeout", "Prepare Week 2 launch"],
        "agent_triggers": [
            {"agent": "idea-factory", "input": {}, "reason": "weekly idea scan"},
        ],
        "budget_allocation": {"toituro": 20},
        "alerts": [],
        "human_needed": [],
        "reasoning": "Business is healthy, focus on growth.",
    }


# ── Unit Tests ────────────────────────────────────────────────────────────────


class TestMetaOrchestratorConfig:
    def test_agent_name(self, orchestrator):
        assert orchestrator.agent_name == "meta_orchestrator"

    def test_default_model_is_opus(self, orchestrator):
        assert orchestrator.default_model == "opus"


class TestPromptLoading:
    def test_load_prompt_returns_string(self):
        prompt = _load_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_prompt_mentions_json_output(self):
        prompt = _load_prompt()
        assert "JSON" in prompt

    def test_prompt_has_day_zero_section(self):
        prompt = _load_prompt()
        assert "JOUR 0" in prompt or "jour 0" in prompt.lower()


class TestGatherMetrics:
    """Test the gather step with mocked DB."""

    @pytest.mark.asyncio
    async def test_gather_returns_required_keys(self, orchestrator):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.agents.meta_orchestrator.SessionLocal", return_value=mock_db):
            ctx = MagicMock(spec=["step_output"])
            result = await orchestrator.gather_all_metrics(ctx)

        assert "businesses" in result
        assert "errors_24h" in result
        assert "budget_yesterday" in result
        assert "timestamp" in result


class TestAnalyzeAndDecide:
    """Test the Claude analysis step with mocked LLM."""

    @pytest.mark.asyncio
    async def test_valid_json_response(self, orchestrator, empty_metrics, valid_decisions):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value=empty_metrics)

        with (
            patch.object(orchestrator, "check_budget", new_callable=AsyncMock, return_value="opus"),
            patch.object(orchestrator, "log_execution", new_callable=AsyncMock),
            patch("src.agents.meta_orchestrator.call_claude", new_callable=AsyncMock) as mock_claude,
        ):
            mock_claude.return_value = (json.dumps(valid_decisions), 0.05)
            result = await orchestrator.analyze_and_decide(ctx)

        decisions = result["decisions"]
        assert "priorities" in decisions
        assert "agent_triggers" in decisions
        assert isinstance(decisions["priorities"], list)

    @pytest.mark.asyncio
    async def test_bad_json_returns_safe_defaults(self, orchestrator, empty_metrics):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value=empty_metrics)

        with (
            patch.object(orchestrator, "check_budget", new_callable=AsyncMock, return_value="sonnet"),
            patch.object(orchestrator, "log_execution", new_callable=AsyncMock),
            patch("src.agents.meta_orchestrator.call_claude", new_callable=AsyncMock) as mock_claude,
        ):
            mock_claude.return_value = ("This is not JSON at all!", 0.02)
            result = await orchestrator.analyze_and_decide(ctx)

        decisions = result["decisions"]
        assert "priorities" in decisions
        assert any("JSON" in a for a in decisions.get("alerts", []))


class TestExecuteDecisions:
    """Test agent triggering and Slack digest."""

    @pytest.mark.asyncio
    async def test_triggers_agents(self, orchestrator, populated_metrics, valid_decisions):
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "analyze_and_decide": {"decisions": valid_decisions, "cost_usd": 0.05},
                "gather_all_metrics": populated_metrics,
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch.object(orchestrator, "log_execution", new_callable=AsyncMock),
            patch("src.agents.meta_orchestrator._send_slack_digest", new_callable=AsyncMock),
            patch("src.agents.meta_orchestrator.SessionLocal", return_value=mock_db),
        ):
            result = await orchestrator.execute_decisions(ctx)

        assert "idea-factory" in result["triggered_agents"]

    @pytest.mark.asyncio
    async def test_handles_trigger_failure_gracefully(self, orchestrator, populated_metrics, valid_decisions):
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "analyze_and_decide": {"decisions": valid_decisions, "cost_usd": 0.05},
                "gather_all_metrics": populated_metrics,
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(side_effect=Exception("Connection refused"))

        with (
            patch.object(orchestrator, "log_execution", new_callable=AsyncMock),
            patch("src.agents.meta_orchestrator._send_slack_digest", new_callable=AsyncMock),
            patch("src.agents.meta_orchestrator.SessionLocal", return_value=mock_db),
        ):
            result = await orchestrator.execute_decisions(ctx)

        assert result["triggered_agents"] == []


class TestSlackDigest:
    @pytest.mark.asyncio
    async def test_skips_when_no_webhook(self):
        with patch("src.agents.meta_orchestrator.settings") as mock_settings:
            mock_settings.SLACK_WEBHOOK_URL = ""
            await _send_slack_digest({"priorities": ["test"]}, [])

    @pytest.mark.asyncio
    async def test_sends_digest_with_businesses(self):
        businesses = [{"mrr": 100.0}, {"mrr": 200.0}]
        decisions = {
            "priorities": ["grow", "optimize", "hire"],
            "agent_triggers": [{"agent": "test", "input": {}}],
            "alerts": ["alert1"],
            "human_needed": ["decision1"],
        }
        with (
            patch("src.agents.meta_orchestrator.settings") as mock_settings,
            patch("src.agents.meta_orchestrator.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock()
            mock_client_cls.return_value = mock_client

            await _send_slack_digest(decisions, businesses)
            mock_client.post.assert_called_once()


class TestDayZeroScenario:
    """The orchestrator should work with zero businesses on day 0."""

    @pytest.mark.asyncio
    async def test_day_zero_triggers_idea_factory(self, orchestrator):
        day0_decisions = {
            "priorities": ["Launch idea discovery — no businesses exist yet"],
            "agent_triggers": [
                {"agent": "idea-factory", "input": {}, "reason": "Day 0 — need to find first idea"},
            ],
            "budget_allocation": {},
            "alerts": [],
            "human_needed": [],
            "reasoning": "No businesses exist. Starting discovery cycle.",
        }

        ctx = MagicMock()
        empty = {
            "businesses": [],
            "snapshots": {},
            "errors_24h": [],
            "error_rates_24h": [],
            "pending_improvements": [],
            "budget_yesterday": {"total_usd": 0, "limit_usd": 50, "by_agent": {}},
            "lead_pipeline": {},
            "timestamp": "2026-03-07T11:00:00+00:00",
        }
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "gather_all_metrics": empty,
                "analyze_and_decide": {"decisions": day0_decisions, "cost_usd": 0.03},
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch.object(orchestrator, "log_execution", new_callable=AsyncMock),
            patch("src.agents.meta_orchestrator._send_slack_digest", new_callable=AsyncMock),
            patch("src.agents.meta_orchestrator.SessionLocal", return_value=mock_db),
        ):
            result = await orchestrator.execute_decisions(ctx)

        assert "idea-factory" in result["triggered_agents"]
