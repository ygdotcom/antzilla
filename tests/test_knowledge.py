"""Tests for the Knowledge Agent and cross-business learning system."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.knowledge_agent import KnowledgeAgent
from src.knowledge import (
    format_knowledge_for_prompt,
    query_knowledge,
    record_knowledge_usage,
    store_knowledge,
)


# ── Knowledge Helper Tests ────────────────────────────────────────────────────


class TestFormatKnowledge:
    def test_empty_returns_empty(self):
        assert format_knowledge_for_prompt([]) == ""

    def test_formats_insights(self):
        insights = [
            {
                "category": "email_template_winner",
                "insight": "Timeline hooks beat pain hooks 2.3x",
                "confidence": 0.85,
                "times_applied": 12,
            }
        ]
        result = format_knowledge_for_prompt(insights)
        assert "CONNAISSANCES" in result
        assert "Timeline hooks" in result
        assert "85%" in result
        assert "12x" in result

    def test_multiple_insights_numbered(self):
        insights = [
            {"category": "a", "insight": "first", "confidence": 0.5, "times_applied": 1},
            {"category": "b", "insight": "second", "confidence": 0.7, "times_applied": 2},
        ]
        result = format_knowledge_for_prompt(insights)
        assert "1." in result
        assert "2." in result


# ── Knowledge Agent Tests ─────────────────────────────────────────────────────


class TestKnowledgeAgentConfig:
    def test_agent_name(self):
        assert KnowledgeAgent().agent_name == "knowledge_agent"

    def test_default_model_is_opus(self):
        assert KnowledgeAgent().default_model == "opus"


class TestScanOutreachExperiments:
    @pytest.mark.asyncio
    async def test_no_experiments_returns_zero(self):
        agent = KnowledgeAgent()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.agents.knowledge_agent.SessionLocal", return_value=mock_db):
            ctx = MagicMock()
            result = await agent.scan_outreach_experiments(ctx)

        assert result["experiments_scanned"] == 0
        assert result["insights_stored"] == 0


class TestSynthesizeWithClaude:
    @pytest.mark.asyncio
    async def test_insufficient_data_skips(self):
        agent = KnowledgeAgent()
        with patch("src.agents.knowledge_agent.query_knowledge", new_callable=AsyncMock) as mock_qk:
            mock_qk.return_value = [{"insight": "x"} for _ in range(3)]  # < 5 needed
            ctx = MagicMock()
            result = await agent.synthesize_with_claude(ctx)
        assert result["meta_insights"] == 0
        assert "Not enough data" in result["reason"]


# ── Deep Scout Knowledge Integration ─────────────────────────────────────────


class TestDeepScoutKnowledge:
    def test_generate_gtm_playbook_queries_knowledge(self):
        """Verify Deep Scout's generate_gtm_playbook uses factory knowledge."""
        import inspect
        from src.agents.deep_scout import DeepScout
        source = inspect.getsource(DeepScout.generate_gtm_playbook)
        assert "query_knowledge" in source
        assert "format_knowledge_for_prompt" in source
        assert "KNOWLEDGE-INFORMED" in source


# ── Outreach Knowledge Integration ───────────────────────────────────────────


class TestOutreachKnowledge:
    def test_outreach_queries_email_winners(self):
        """Verify Outreach Agent queries winning email templates."""
        import inspect
        from src.agents.distribution.outreach import OutreachAgent
        source = inspect.getsource(OutreachAgent.run_outreach)
        assert "query_knowledge" in source
        assert "email_template_winner" in source

    def test_outreach_prompt_mentions_knowledge(self):
        from src.agents.distribution.outreach import OUTREACH_SYSTEM_PROMPT
        assert "CONNAISSANCES" in OUTREACH_SYSTEM_PROMPT or "connaissances" in OUTREACH_SYSTEM_PROMPT.lower()


# ── Idea Factory Knowledge Integration ───────────────────────────────────────


class TestIdeaFactoryKnowledge:
    def test_idea_factory_queries_calibrations(self):
        """Verify Idea Factory includes scoring calibrations."""
        import inspect
        from src.agents.idea_factory import IdeaFactory
        source = inspect.getsource(IdeaFactory.filter_canadian_gap)
        assert "idea_scoring_calibration" in source
        assert "query_knowledge" in source


# ── Reply Handler Knowledge Integration ──────────────────────────────────────


class TestReplyHandlerKnowledge:
    def test_reply_handler_stores_winning_responses(self):
        """Verify Reply Handler stores objection→conversion patterns."""
        import inspect
        from src.agents.distribution.reply_handler import ReplyHandler
        source = inspect.getsource(ReplyHandler.process_replies)
        assert "store_knowledge" in source
        assert "objection_response" in source

    def test_reply_handler_queries_past_responses(self):
        """Verify Reply Handler enriches prompt with past objection winners."""
        import inspect
        from src.agents.distribution.reply_handler import ReplyHandler
        source = inspect.getsource(ReplyHandler.process_replies)
        assert "query_knowledge" in source
        assert "format_knowledge_for_prompt" in source


# ── Dashboard Knowledge Page ─────────────────────────────────────────────────


class TestKnowledgeDashboard:
    def test_knowledge_route_exists(self):
        from src.dashboard.routes.knowledge import router
        paths = [r.path for r in router.routes]
        assert any("knowledge" in str(p) or p == "" for p in paths)

    def test_add_insight_endpoint_exists(self):
        from src.dashboard.routes.knowledge import router
        paths = [r.path for r in router.routes]
        assert any("add" in p for p in paths)

    def test_outdated_endpoint_exists(self):
        from src.dashboard.routes.knowledge import router
        paths = [r.path for r in router.routes]
        assert any("outdated" in p for p in paths)

    def test_knowledge_template_exists(self):
        from pathlib import Path
        tmpl = Path(__file__).parent.parent / "src" / "dashboard" / "templates" / "knowledge.html"
        assert tmpl.exists()


# ── Migration Tests ──────────────────────────────────────────────────────────


class TestKnowledgeMigration:
    def test_factory_knowledge_table_in_migration(self):
        from pathlib import Path
        sql = (Path(__file__).parent.parent / "migrations" / "001_init.sql").read_text()
        assert "CREATE TABLE factory_knowledge" in sql
        assert "email_template_winner" in sql
        assert "channel_effectiveness" in sql
        assert "objection_response" in sql
        assert "idea_scoring_calibration" in sql
        assert "confidence" in sql
        assert "times_applied" in sql

    def test_knowledge_indexes_exist(self):
        from pathlib import Path
        sql = (Path(__file__).parent.parent / "migrations" / "001_init.sql").read_text()
        assert "idx_factory_knowledge_category" in sql
        assert "idx_factory_knowledge_confidence" in sql


class TestKnowledgeCompounds:
    """The core design goal: by Business #5, the factory is smarter than Business #1."""

    def test_format_includes_confidence_and_usage(self):
        insights = [{
            "category": "channel_effectiveness",
            "insight": "Facebook Groups has 3x lower CAC than cold email for trades",
            "confidence": 0.92,
            "times_applied": 4,
        }]
        text = format_knowledge_for_prompt(insights)
        assert "92%" in text
        assert "4x" in text

    def test_knowledge_categories_cover_full_lifecycle(self):
        """All 10 categories span discovery→distribution→retention."""
        from pathlib import Path
        sql = (Path(__file__).parent.parent / "migrations" / "001_init.sql").read_text()
        categories = [
            "email_template_winner",     # distribution
            "channel_effectiveness",     # distribution
            "idea_scoring_calibration",  # discovery
            "objection_response",        # distribution
            "icp_insight",               # discovery
            "pricing_insight",           # monetization
            "content_format_winner",     # marketing
            "onboarding_pattern",        # activation
            "churn_reason",              # retention
            "referral_tactic",           # growth
        ]
        for cat in categories:
            assert cat in sql, f"Category '{cat}' missing from migration"
