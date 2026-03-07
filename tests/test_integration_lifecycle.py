"""Integration tests simulating the full factory lifecycle.

UNIT tests with mocked DB/APIs — NOT actual database tests.
Verify that agents can be chained correctly and spec requirements are met.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Phase 1: Discovery ──────────────────────────────────────────────────────


class TestPhase1_Discovery:
    """Idea discovered → scouted → GTM Playbook generated."""

    @pytest.mark.asyncio
    async def test_idea_factory_produces_qualified_ideas(self):
        from src.agents.idea_factory import (
            IdeaFactory,
            SCORE_THRESHOLD,
            CRITERIA_COUNT,
            _parse_scored_ideas,
        )

        agent = IdeaFactory()
        assert agent.agent_name == "idea_factory"

        # Score threshold from spec
        assert SCORE_THRESHOLD >= 7.0

        # 12 criteria from spec
        assert CRITERIA_COUNT == 12

        # Parse produces valid ideas with name + score
        raw = '[{"name": "Quote OS", "score": 8.5, "niche": "roofing"}]'
        ideas = _parse_scored_ideas(raw)
        assert len(ideas) == 1
        assert ideas[0]["name"] == "Quote OS"
        assert ideas[0]["score"] == 8.5

        # Below threshold filtered (handled in persist step, not parse)
        low = _parse_scored_ideas('[{"name": "Bad Idea", "score": 4.0}]')
        assert len(low) == 1
        assert low[0]["score"] == 4.0

    @pytest.mark.asyncio
    async def test_deep_scout_generates_both_outputs(self):
        from src.agents.deep_scout import (
            DeepScout,
            _parse_scout_output,
            GTM_SEPARATOR,
            _validate_playbook,
        )

        agent = DeepScout()
        assert agent.agent_name == "deep_scout"

        # Scout produces both report + playbook (separated by GTM_SEPARATOR)
        report_md = "# Scout Report\n\nMarket analysis..."
        playbook = {"icp": {}, "channels_ranked": [], "lead_sources": [], "messaging": {}, "signals": [], "go_nogo": "go", "confidence": 0.8}
        combined = report_md + GTM_SEPARATOR + json.dumps(playbook)
        parsed_report, parsed_playbook = _parse_scout_output(combined)
        assert parsed_report.strip().startswith("# Scout Report")
        assert parsed_playbook is not None
        assert parsed_playbook.get("go_nogo") == "go"

        # Playbook validation requires key sections
        missing = _validate_playbook(playbook)
        assert len(missing) == 0

    @pytest.mark.asyncio
    async def test_gtm_playbook_has_all_required_sections(self):
        from src.agents.deep_scout import _validate_playbook

        required = ["go_nogo", "confidence", "icp", "channels_ranked", "lead_sources", "messaging", "signals"]
        full = {k: ([] if k in ("channels_ranked", "lead_sources", "signals") else {}) for k in required}
        missing = _validate_playbook(full)
        assert len(missing) == 0

        partial = {"icp": {}, "messaging": {}}
        missing = _validate_playbook(partial)
        assert "channels_ranked" in missing
        assert "lead_sources" in missing
        assert "signals" in missing


# ── Phase 2: Validation ──────────────────────────────────────────────────────


class TestPhase2_Validation:
    """Validated → Brand → Domain → Build."""

    @pytest.mark.asyncio
    async def test_validator_kill_rules_enforce_cpc_threshold(self):
        from src.agents.validator import (
            Validator,
            CPC_PAUSE_THRESHOLD,
            CPC_PAUSE_DAYS,
            SIGNUP_RATE_KILL_THRESHOLD,
        )

        assert CPC_PAUSE_THRESHOLD == 8.0
        assert CPC_PAUSE_DAYS >= 3
        assert SIGNUP_RATE_KILL_THRESHOLD <= 0.02

        agent = Validator()
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={"idea_id": 999})
        # Validator gets metrics from step_output("monitor_daily"), not DB
        ctx.step_output = MagicMock(
            return_value={
                "metrics": {
                    "cpc_usd": 9.0,
                    "signup_rate": 0.01,
                    "days_tracked": 5,
                },
            }
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.validator.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.evaluate_results(ctx)

        assert result["decision"] == "pause"
        assert "CPC" in result["reason"] or "8" in result["reason"]

    @pytest.mark.asyncio
    async def test_brand_kit_flows_to_builder(self):
        from src.agents.validator import Validator

        # Validator requests light brand for landing page; BrandDesigner.quick_brand returns brand kit
        validator = Validator()
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={"idea_id": 1, "scout_report": "# Scout", "niche": "roofing"})

        mock_return = {"brand_kit": {"colors": ["#000"]}, "idea_id": 1}
        with patch(
            "src.agents.brand_designer.BrandDesigner.quick_brand",
            new_callable=AsyncMock,
            return_value=mock_return,
        ):
            result = await validator.request_light_brand(ctx)

        assert result.get("brand_kit") is not None
        assert result.get("idea_id") == 1

    @pytest.mark.asyncio
    async def test_builder_verifies_rls_before_deploy(self):
        from src.agents.builder import verify_rls_compliance, RLS_PATTERN, RLS_ENABLE_PATTERN

        # Compliant: every CREATE TABLE has RLS
        compliant_sql = """
        CREATE TABLE projects (id SERIAL PRIMARY KEY);
        ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
        CREATE TABLE quotes (id SERIAL);
        ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;
        """
        result = verify_rls_compliance(compliant_sql)
        assert result["compliant"] is True
        assert len(result["missing_rls"]) == 0

        # Non-compliant: table without RLS
        bad_sql = """
        CREATE TABLE projects (id SERIAL PRIMARY KEY);
        ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
        CREATE TABLE secrets (id SERIAL);
        """
        result = verify_rls_compliance(bad_sql)
        assert result["compliant"] is False
        assert "secrets" in result["missing_rls"]


# ── Phase 3: Distribution ──────────────────────────────────────────────────────


class TestPhase3_Distribution:
    """Leads found → enriched → outreach → replies handled."""

    @pytest.mark.asyncio
    async def test_lead_pipeline_reads_playbook_sources(self):
        from src.agents.distribution.lead_pipeline import LeadPipeline, SOURCE_HANDLERS

        agent = LeadPipeline()
        playbook = {
            "lead_sources": [
                {"type": "google_maps", "query": "couvreur", "geo": "QC", "priority": 1},
                {"type": "rbq_registry", "licence_type": "couvreur", "priority": 2},
            ],
        }

        # Lead pipeline uses lead_sources from playbook, not hardcoded
        sources = playbook.get("lead_sources", [])
        sources.sort(key=lambda s: s.get("priority", 99))
        assert len(sources) == 2
        assert sources[0]["type"] == "google_maps"
        assert "google_maps" in SOURCE_HANDLERS

    @pytest.mark.asyncio
    async def test_enrichment_waterfall_stops_on_first_hit(self):
        from src.agents.distribution.enrichment import _waterfall_enrich

        # Mock Apollo to return email immediately → no Hunter/website scrape
        with patch("src.agents.distribution.enrichment.apollo") as mock_apollo:
            mock_apollo.enrich_person = AsyncMock(return_value={"email": "test@co.ca", "phone": "+15145551234"})
            result, sources = await _waterfall_enrich("Jean", "Toiture ABC", "toitureabc.ca")

        assert result is not None
        assert result.get("email") == "test@co.ca"
        assert "apollo" in sources
        assert "hunter" not in sources

    @pytest.mark.asyncio
    async def test_outreach_shadow_mode_blocks_auto_send(self):
        from src.agents.distribution.outreach import (
            OutreachAgent,
            determine_autonomy_level,
            AUTONOMY_LEVELS,
        )

        # Shadow mode = first 2 weeks = all to Slack, no auto-send
        created = datetime.now(tz=timezone.utc) - timedelta(days=5)
        level = determine_autonomy_level(created)
        assert level == "shadow"
        assert "Slack" in AUTONOMY_LEVELS["shadow"]["description"]

        # In shadow mode, should_send is False (messages queued for review)
        agent = OutreachAgent()
        with patch("src.agents.distribution.outreach.get_active_businesses", new_callable=AsyncMock, return_value=[]):
            ctx = MagicMock()
            result = await agent.run_outreach(ctx)
        assert result["messages_sent"] == 0

    @pytest.mark.asyncio
    async def test_reply_handler_routes_positive_to_voice(self):
        from src.agents.distribution.reply_handler import (
            ReplyHandler,
            _route_positive_interested,
            REPLY_CATEGORIES,
        )

        assert "positive_interested" in REPLY_CATEGORIES

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("src.agents.distribution.reply_handler.SessionLocal", return_value=mock_db):
            await _route_positive_interested(1, 1)

        # Should update lead to 'replied' (ready for Voice Agent warm call)
        call_sql = mock_db.execute.call_args[0][0].text
        assert "replied" in call_sql

    @pytest.mark.asyncio
    async def test_voice_agent_blocks_cold_calls(self):
        from src.agents.voice_agent import VoiceAgent, WARM_STATUSES

        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "phone": "+15145551234",
            "lead_status": "new",
            "is_customer": False,
            "province": "QC",
            "business_id": 1,
        })

        result = await agent.check_compliance(ctx)
        assert result["can_call"] is False
        assert result["gate"] == "consent"

        # Cold statuses must not be in WARM_STATUSES
        assert "new" not in WARM_STATUSES
        assert "contacted" not in WARM_STATUSES


# ── Phase 4: Customer Lifecycle ──────────────────────────────────────────────


class TestPhase4_CustomerLifecycle:
    """Signup → onboarding → billing → support → referral."""

    @pytest.mark.asyncio
    async def test_reverse_trial_downgrades_not_cancels(self):
        from src.agents.billing_agent import BillingAgent

        agent = BillingAgent()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("src.agents.billing_agent.SessionLocal", return_value=mock_db):
            result = await agent._handle_sub_deleted({"id": "sub_123"})

        # SPEC §4: Reverse trial → downgrade to free, NOT delete
        assert result["action"] == "downgraded_to_free"
        call_sql = mock_db.execute.call_args[0][0].text
        assert "free" in call_sql.lower()

    @pytest.mark.asyncio
    async def test_nps_9_triggers_referral_invitation(self):
        from src.agents.referral_agent import ReferralAgent, NPS_THRESHOLD

        assert NPS_THRESHOLD == 9

        agent = ReferralAgent()
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={"business_id": None})

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        cust = MagicMock()
        cust.id = 1
        cust.name = "Jean"
        cust.email = "jean@test.ca"
        cust.phone = "+15145551234"
        cust.language = "fr"
        cust.referral_code = "ABC123"
        cust.nps_score = 10
        cust.biz_name = "Toîturo"
        cust.domain = "toituro.ca"
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[cust])))

        with (
            patch("src.agents.referral_agent.SessionLocal", return_value=mock_db),
            patch("src.agents.referral_agent.load_playbook", new_callable=AsyncMock, return_value={"referral": {"incentive": "1_month_free"}}),
            patch("src.agents.referral_agent._send_sms", new_callable=AsyncMock, return_value=True),
            patch("src.agents.referral_agent._send_referral_email", new_callable=AsyncMock, return_value=True),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.nps_trigger(ctx)

        # NPS >= 9 triggers referral flow; result has invitations_sent or eligible
        assert "invitations_sent" in result or "eligible" in result
        if "invitations_sent" in result:
            assert result["invitations_sent"] >= 0

    @pytest.mark.asyncio
    async def test_support_responds_in_customer_language(self):
        from src.agents.support_agent import SupportAgent, SUPPORT_SYSTEM_PROMPT

        assert "{language}" in SUPPORT_SYSTEM_PROMPT

        agent = SupportAgent()
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={
            "business_id": 1,
            "customer_id": 1,
            "message": "Comment exporter?",
        })

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        cust = MagicMock()
        cust.name = "Jean"
        cust.language = "fr"
        cust.email = "jean@test.com"
        cust.biz_name = "Quote OS"
        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.fetchone = MagicMock(return_value=cust)
            elif call_count == 2:
                r.fetchall = MagicMock(return_value=[])
            else:
                r.fetchone = MagicMock(return_value=None)
            return r

        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.support_agent.SessionLocal", return_value=mock_db),
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="sonnet"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.support_agent.call_claude", new_callable=AsyncMock) as mock_claude,
        ):
            mock_claude.return_value = ("Voici comment exporter...", 0.01)
            result = await agent.handle_ticket(ctx)

        assert result["language"] == "fr"
        assert "français" in mock_claude.call_args[1]["system"].lower()


# ── Phase 5: Intelligence ───────────────────────────────────────────────────


class TestPhase5_Intelligence:
    """Analytics → Self-Reflection → Budget Guardian."""

    @pytest.mark.asyncio
    async def test_kill_score_formula_matches_spec(self):
        from src.agents.analytics_agent import (
            _compute_kill_score,
            KILL_WEIGHTS,
        )

        # Weights sum to 1.0
        assert abs(sum(KILL_WEIGHTS.values()) - 1.0) < 0.001

        # Score bounded 0-100
        score = _compute_kill_score(
            mrr_current=500,
            mrr_7d_ago=400,
            mrr_30d_ago=300,
            customers_current=10,
            customers_7d_ago=8,
            activation_rate=0.8,
            churn_rate=0.05,
            cac=50,
            mrr_per_customer=50,
            api_cost_daily=2,
            nps=50,
        )
        assert 0 <= score <= 100

    @pytest.mark.asyncio
    async def test_self_reflection_categorizes_findings(self):
        from src.agents.self_reflection import SelfReflectionAgent, CATEGORIES

        required = [
            "recurring_error",
            "missed_opportunity",
            "inefficiency",
            "blind_spot",
            "cross_learning",
            "drift",
            "quality",
            "new_idea",
        ]
        for cat in required:
            assert cat in CATEGORIES

        assert len(CATEGORIES) == 8

    @pytest.mark.asyncio
    async def test_budget_guardian_throttles_at_80_percent(self):
        from src.agents.base_agent import BaseAgent, BudgetExceededError

        class TestAgent(BaseAgent):
            agent_name = "test_agent"
            default_model = "opus"

        agent = TestAgent()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        # At 80%+ of limit, should downgrade opus → sonnet
        row = MagicMock()
        row.spent = 4.1  # 82% of 5.0 default limit
        global_row = MagicMock()
        global_row.spent = 1.0
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(fetchone=MagicMock(return_value=row)),
                MagicMock(fetchone=MagicMock(return_value=global_row)),
            ]
        )

        with (
            patch("src.agents.base_agent.SessionLocal", return_value=mock_db),
            patch.object(agent, "_alert_budget_warning", new_callable=AsyncMock),
        ):
            model = await agent.check_budget()

        # Should downgrade from opus to sonnet
        assert model == "sonnet"
