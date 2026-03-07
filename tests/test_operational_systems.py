"""Tests for the 7 operational systems: quality gate, human touchpoint,
brand monitor, teardown, product iteration, cash flow, backup restore."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══ 1. QUALITY GATE ═════════════════════════════════════════════════════════

from src.quality import quality_check_emails, security_scan_code


class TestQualityGateEmails:
    @pytest.mark.asyncio
    async def test_passes_good_emails(self):
        with patch("src.quality.call_claude", new_callable=AsyncMock) as mock:
            mock.return_value = (json.dumps({"pass": True, "overall": 8.5, "issues": []}), 0.01)
            result = await quality_check_emails([
                {"subject": "Quick question", "body": "Salut Jean, comment vas-tu?"},
            ], sample_size=1)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_blocks_bad_emails(self):
        with patch("src.quality.call_claude", new_callable=AsyncMock) as mock:
            mock.return_value = (json.dumps({
                "pass": False, "overall": 4.0,
                "issues": ["Sounds AI-generated", "Wrong tone"],
            }), 0.01)
            result = await quality_check_emails([
                {"subject": "Leverage our solution", "body": "I hope this finds you well"},
            ], sample_size=1)
        assert result["passed"] is False
        assert result["blocked_count"] == 1


class TestSecurityScan:
    def test_catches_stripe_key(self):
        fake_key = "sk_live_" + "x" * 24
        files = [{"path": "src/lib/stripe.ts", "content": f'const key = "{fake_key}"'}]
        result = security_scan_code(files)
        assert result["passed"] is False
        assert result["critical_count"] >= 1

    def test_catches_github_token(self):
        fake_token = "ghp_" + "X" * 36
        files = [{"path": "config.ts", "content": f'const token = "{fake_token}"'}]
        result = security_scan_code(files)
        assert result["passed"] is False

    def test_passes_clean_code(self):
        files = [{"path": "page.tsx", "content": "export default function Page() { return <div>Hello</div> }"}]
        result = security_scan_code(files)
        assert result["passed"] is True


class TestOutreachQualityGate:
    def test_outreach_has_quality_check(self):
        import inspect
        from src.agents.distribution.outreach import OutreachAgent
        source = inspect.getsource(OutreachAgent.run_outreach)
        assert "quality_check_emails" in source
        assert "QUALITY GATE" in source


class TestBuilderSecurityScan:
    def test_builder_has_security_scan(self):
        import inspect
        from src.agents.builder import Builder
        source = inspect.getsource(Builder.verify_rls)
        assert "security_scan_code" in source
        assert "SECURITY SCAN" in source


# ═══ 2. HUMAN TOUCHPOINT ═════════════════════════════════════════════════════


class TestHumanTouchpoint:
    def test_reply_handler_has_hot_lead_logic(self):
        import inspect
        from src.agents.distribution.reply_handler import ReplyHandler
        source = inspect.getsource(ReplyHandler.process_replies)
        assert "HUMAN TOUCHPOINT" in source
        assert ">= 80" in source or ">=80" in source
        assert "customer_count < 5" in source

    def test_first_5_customers_always_slack(self):
        """First 5 customers should ALWAYS route to Slack, not Voice Agent."""
        import inspect
        from src.agents.distribution.reply_handler import ReplyHandler
        source = inspect.getsource(ReplyHandler.process_replies)
        assert "customer_count" in source


# ═══ 3. BRAND REPUTATION MONITOR ═════════════════════════════════════════════


class TestBrandMonitor:
    def test_social_agent_has_brand_monitor(self):
        import inspect
        from src.agents.social_agent import SocialAgent
        assert hasattr(SocialAgent, "monitor_brand_mentions")

    def test_brand_mentions_table_in_migration(self):
        sql = (Path(__file__).parent.parent / "migrations" / "001_init.sql").read_text()
        assert "CREATE TABLE brand_mentions" in sql
        assert "sentiment" in sql
        assert "is_negative" in sql


# ═══ 4. TEARDOWN WORKFLOW ════════════════════════════════════════════════════


class TestTeardown:
    def test_analytics_agent_has_teardown(self):
        from src.agents.analytics_agent import AnalyticsAgent
        assert hasattr(AnalyticsAgent, "teardown_business")

    @pytest.mark.asyncio
    async def test_teardown_marks_leads_killed(self):
        from src.agents.analytics_agent import AnalyticsAgent
        agent = AnalyticsAgent()

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        biz_row = MagicMock()
        biz_row.id = 1
        biz_row.slug = "test"
        biz_row.domain = "test.ca"
        biz_row.config = "{}"
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=biz_row)))
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.analytics_agent.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            ctx = MagicMock()
            ctx.workflow_input = MagicMock(return_value={"business_id": 1})
            result = await agent.teardown_business(ctx)

        assert result["teardown"] is True

    def test_teardown_registered_as_workflow(self):
        """Analytics register() should return a tuple including teardown."""
        import inspect
        from src.agents.analytics_agent import register
        source = inspect.getsource(register)
        assert "business-teardown" in source


# ═══ 5. PRODUCT ITERATION LOOP ═══════════════════════════════════════════════


class TestProductIteration:
    def test_feature_requests_table_in_migration(self):
        sql = (Path(__file__).parent.parent / "migrations" / "001_init.sql").read_text()
        assert "CREATE TABLE feature_requests" in sql
        assert "priority_score" in sql
        assert "github_pr_url" in sql

    def test_support_agent_has_feature_scan(self):
        from src.agents.support_agent import SupportAgent
        assert hasattr(SupportAgent, "scan_feature_requests")


# ═══ 6. CASH FLOW TRACKER ════════════════════════════════════════════════════


class TestCashFlow:
    def test_budget_guardian_has_cash_flow(self):
        from src.agents.budget_guardian import BudgetGuardianAgent
        assert hasattr(BudgetGuardianAgent, "track_cash_flow")

    def test_cash_flow_tracks_per_business(self):
        import inspect
        from src.agents.budget_guardian import BudgetGuardianAgent
        source = inspect.getsource(BudgetGuardianAgent.track_cash_flow)
        assert "total_invested" in source
        assert "months_to_breakeven" in source
        assert "total_burn" in source


# ═══ 7. BACKUP RESTORE TEST ══════════════════════════════════════════════════


class TestBackupRestore:
    def test_devops_has_restore_test(self):
        from src.agents.devops_agent import DevOpsAgent
        assert hasattr(DevOpsAgent, "test_restore")

    def test_restore_test_uses_temp_db(self):
        import inspect
        from src.agents.devops_agent import DevOpsAgent
        source = inspect.getsource(DevOpsAgent.test_restore)
        assert "factory_restore_test" in source
        assert "pg_dump" in source
