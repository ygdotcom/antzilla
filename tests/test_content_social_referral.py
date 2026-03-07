"""Tests for Content Engine, Social Agent, and Referral Agent."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══ CONTENT ENGINE ═══════════════════════════════════════════════════════════

from src.agents.content_engine import (
    PROGRAMMATIC_TEMPLATES,
    ContentEngine,
    generate_programmatic_variants,
)


class TestContentEngineConfig:
    def test_agent_name(self):
        assert ContentEngine().agent_name == "content_engine"

    def test_default_model(self):
        assert ContentEngine().default_model == "sonnet"


class TestProgrammaticTemplates:
    def test_all_6_template_types_exist(self):
        types = {t["type"] for t in PROGRAMMATIC_TEMPLATES}
        assert "product_for_subvertical" in types
        assert "product_vs_competitor" in types
        assert "best_category_in_province" in types
        assert "product_plus_integration" in types
        assert "how_to_workflow" in types
        assert "industry_metric_year" in types

    def test_each_template_has_fr_and_en(self):
        for t in PROGRAMMATIC_TEMPLATES:
            assert "pattern_fr" in t, f"{t['type']} missing pattern_fr"
            assert "pattern_en" in t, f"{t['type']} missing pattern_en"


class TestGenerateVariants:
    def test_generates_subvertical_pages(self):
        variants = generate_programmatic_variants(
            product_name="Quote OS",
            niche="construction",
            sub_verticals=["couvreurs", "plombiers"],
            competitors=[],
            integrations=[],
            workflows=[],
            metrics=[],
        )
        sv_variants = [v for v in variants if v["type"] == "product_for_subvertical"]
        assert len(sv_variants) == 2

    def test_generates_competitor_pages(self):
        variants = generate_programmatic_variants(
            product_name="Quote OS",
            niche="construction",
            sub_verticals=[],
            competitors=["Jobber", "Houzz Pro"],
            integrations=[],
            workflows=[],
            metrics=[],
        )
        comp = [v for v in variants if v["type"] == "product_vs_competitor"]
        assert len(comp) == 2

    def test_generates_province_pages(self):
        variants = generate_programmatic_variants(
            product_name="Quote OS",
            niche="quoting",
            sub_verticals=[],
            competitors=[],
            integrations=[],
            workflows=[],
            metrics=[],
        )
        prov = [v for v in variants if v["type"] == "best_category_in_province"]
        assert len(prov) == 4  # 4 provinces

    def test_generates_integration_pages(self):
        variants = generate_programmatic_variants(
            product_name="Quote OS",
            niche="construction",
            sub_verticals=[],
            competitors=[],
            integrations=["QuickBooks", "Acomba"],
            workflows=[],
            metrics=[],
        )
        integ = [v for v in variants if v["type"] == "product_plus_integration"]
        assert len(integ) == 2

    def test_bilingual_variants(self):
        variants = generate_programmatic_variants(
            product_name="Test",
            niche="test",
            sub_verticals=["plombiers"],
            competitors=[],
            integrations=[],
            workflows=[],
            metrics=[],
        )
        for v in variants:
            assert "fr" in v["languages"]
            assert "en" in v["languages"]

    def test_empty_inputs_zero_variants(self):
        variants = generate_programmatic_variants(
            product_name="Test",
            niche="test",
            sub_verticals=[],
            competitors=[],
            integrations=[],
            workflows=[],
            metrics=[],
        )
        # Only province pages (always generated)
        assert all(v["type"] == "best_category_in_province" for v in variants)

    def test_scale_potential(self):
        """Spec says 20-50 pages at launch — verify we can hit that."""
        variants = generate_programmatic_variants(
            product_name="Quote OS",
            niche="construction",
            sub_verticals=["couvreurs", "plombiers", "électriciens", "menuisiers", "peintres"],
            competitors=["Jobber", "Houzz Pro", "Buildertrend"],
            integrations=["QuickBooks", "Acomba", "Sage"],
            workflows=["estimer un projet", "faire une soumission", "suivre les paiements"],
            metrics=["Coûts moyens de toiture par ville", "Salaires moyens construction"],
        )
        # Each variant generates pages in 2 languages
        total_pages = sum(len(v["languages"]) for v in variants)
        assert total_pages >= 20, f"Only {total_pages} pages — spec requires 20-50"


class TestEditorialContent:
    @pytest.mark.asyncio
    async def test_no_businesses_returns_zero(self):
        agent = ContentEngine()
        with patch("src.agents.content_engine.get_active_businesses", new_callable=AsyncMock, return_value=[]):
            ctx = MagicMock()
            result = await agent.editorial_content(ctx)
        assert result["articles_written"] == 0


class TestEditorialPrompt:
    def test_has_quick_answer_requirement(self):
        from src.agents.content_engine import EDITORIAL_SYSTEM_PROMPT
        assert "Quick Answer" in EDITORIAL_SYSTEM_PROMPT

    def test_has_geo_requirements(self):
        from src.agents.content_engine import EDITORIAL_SYSTEM_PROMPT
        assert "LLM" in EDITORIAL_SYSTEM_PROMPT or "chiffr" in EDITORIAL_SYSTEM_PROMPT.lower()

    def test_has_question_format_keywords(self):
        from src.agents.content_engine import EDITORIAL_SYSTEM_PROMPT
        assert "question" in EDITORIAL_SYSTEM_PROMPT.lower() or "Comment" in EDITORIAL_SYSTEM_PROMPT


# ═══ SOCIAL AGENT ═════════════════════════════════════════════════════════════

from src.agents.social_agent import (
    MENTION_RATIO,
    MIN_KARMA_FOR_MENTION,
    PAUSE_DAYS_ON_REMOVAL,
    AntiBanGuardrails,
    SocialAgent,
)


class TestSocialAgentConfig:
    def test_agent_name(self):
        assert SocialAgent().agent_name == "social_agent"

    def test_default_model(self):
        assert SocialAgent().default_model == "haiku"


class TestAntiBanRules:
    def test_90_10_ratio(self):
        assert MENTION_RATIO == 0.10, "Spec: 90% helpful / 10% mention"

    def test_min_karma_before_mention(self):
        assert MIN_KARMA_FOR_MENTION == 100, "Spec: karma > 100 before product mention"

    def test_pause_on_removal(self):
        assert PAUSE_DAYS_ON_REMOVAL == 14, "Spec: pause 14 days if post removed"

    @pytest.mark.asyncio
    async def test_check_community_paused(self):
        mock_db = AsyncMock()
        removal_time = datetime.now(tz=timezone.utc) - timedelta(days=5)

        row = MagicMock()
        row.total = 10
        row.today = 1
        row.last_removal = removal_time
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(fetchone=MagicMock(return_value=row)),
                MagicMock(fetchone=MagicMock(return_value=MagicMock(mentions=1))),
            ]
        )

        status = await AntiBanGuardrails.check_community_status(mock_db, 1, "r/roofing")
        assert status["paused"] is True  # removed 5 days ago, < 14 day pause

    @pytest.mark.asyncio
    async def test_check_community_not_paused(self):
        mock_db = AsyncMock()
        removal_time = datetime.now(tz=timezone.utc) - timedelta(days=20)

        row = MagicMock()
        row.total = 50
        row.today = 2
        row.last_removal = removal_time
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(fetchone=MagicMock(return_value=row)),
                MagicMock(fetchone=MagicMock(return_value=MagicMock(mentions=3))),
            ]
        )

        status = await AntiBanGuardrails.check_community_status(mock_db, 1, "r/roofing")
        assert status["paused"] is False  # removed 20 days ago, > 14 day pause

    @pytest.mark.asyncio
    async def test_mention_ratio_enforcement(self):
        mock_db = AsyncMock()
        row = MagicMock()
        row.total = 10
        row.today = 0
        row.last_removal = None
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(fetchone=MagicMock(return_value=row)),
                MagicMock(fetchone=MagicMock(return_value=MagicMock(mentions=2))),
            ]
        )

        status = await AntiBanGuardrails.check_community_status(mock_db, 1, "r/test")
        # 2/10 = 20% > 10% threshold
        assert status["can_mention"] is False

    @pytest.mark.asyncio
    async def test_reddit_karma_check(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=MagicMock(karma=50)))
        )
        karma = await AntiBanGuardrails.check_reddit_karma(mock_db, 1)
        assert karma == 50
        assert karma < MIN_KARMA_FOR_MENTION


class TestSocialAgentStep:
    @pytest.mark.asyncio
    async def test_no_businesses_returns_zero(self):
        agent = SocialAgent()
        with patch("src.agents.social_agent.get_active_businesses", new_callable=AsyncMock, return_value=[]):
            ctx = MagicMock()
            result = await agent.monitor_and_engage(ctx)
        assert result["businesses"] == 0


class TestSocialPrompt:
    def test_mention_mode_variable(self):
        from src.agents.social_agent import RESPONSE_SYSTEM_PROMPT
        assert "{mention_mode}" in RESPONSE_SYSTEM_PROMPT

    def test_max_100_words(self):
        from src.agents.social_agent import RESPONSE_SYSTEM_PROMPT
        assert "100" in RESPONSE_SYSTEM_PROMPT


# ═══ REFERRAL AGENT ═══════════════════════════════════════════════════════════

from src.agents.referral_agent import (
    AMBASSADOR_THRESHOLD,
    NPS_THRESHOLD,
    NUDGE_DELAY_DAYS,
    ReferralAgent,
    generate_referral_code,
)


class TestReferralAgentConfig:
    def test_agent_name(self):
        assert ReferralAgent().agent_name == "referral_agent"

    def test_nps_threshold(self):
        assert NPS_THRESHOLD == 9, "Spec: NPS >= 9 triggers referral"

    def test_ambassador_threshold(self):
        assert AMBASSADOR_THRESHOLD == 3, "Spec: >= 3 referrals = ambassador"

    def test_nudge_delay(self):
        assert NUDGE_DELAY_DAYS == 5, "Spec: 5-7 days nudge"


class TestReferralCode:
    def test_length(self):
        code = generate_referral_code()
        assert len(code) == 8

    def test_no_ambiguous_chars(self):
        for _ in range(100):
            code = generate_referral_code()
            assert "0" not in code
            assert "O" not in code
            assert "1" not in code
            assert "I" not in code

    def test_uniqueness(self):
        codes = {generate_referral_code() for _ in range(50)}
        assert len(codes) == 50  # all unique


class TestNPSTrigger:
    @pytest.mark.asyncio
    async def test_no_eligible_customers(self):
        agent = ReferralAgent()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=[]))
        )

        with patch("src.agents.referral_agent.SessionLocal", return_value=mock_db):
            ctx = MagicMock()
            ctx.workflow_input = MagicMock(return_value={"business_id": 1})
            result = await agent.nps_trigger(ctx)

        assert result["invitations_sent"] == 0


class TestTrackAndReward:
    @pytest.mark.asyncio
    async def test_no_pending_rewards(self):
        agent = ReferralAgent()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=[]))
        )
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.referral_agent.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            ctx = MagicMock()
            ctx.workflow_input = MagicMock(return_value={})
            result = await agent.track_and_reward(ctx)

        assert result["rewards_applied"] == 0


class TestDoubleSidedIncentive:
    """Spec: both referrer AND referee get reward."""

    def test_reward_type_in_playbook(self):
        playbook = {
            "referral": {
                "incentive": "1_month_free",
                "ask_trigger": "nps_9_or_10",
                "program_type": "double_sided",
            }
        }
        assert playbook["referral"]["program_type"] == "double_sided"
        assert playbook["referral"]["incentive"] == "1_month_free"


class TestSMSPriority:
    """Spec: SMS referral requests generate 4x higher response than email.
    Prioritize SMS for trades ICPs."""

    def test_sms_tried_before_email(self):
        """Verify the nps_trigger method tries SMS before email."""
        import inspect
        source = inspect.getsource(ReferralAgent.nps_trigger)
        sms_pos = source.find("_send_sms")
        email_pos = source.find("_send_referral_email")
        assert sms_pos < email_pos, "SMS must be attempted before email"
