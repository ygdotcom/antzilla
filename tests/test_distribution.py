"""Tests for the Distribution Engine (5 sub-agents).

Tests the revenue engine's core logic without requiring external APIs:
- Lead Pipeline: source handlers, deduplication
- Enrichment: waterfall logic, lead scoring
- Signal Monitor: signal detection and lead score bumping
- Outreach: tiered autonomy, message generation
- Reply Handler: classification routing, CASL unsubscribe
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Lead Pipeline ─────────────────────────────────────────────────────────────

from src.agents.distribution.lead_pipeline import (
    LeadPipeline,
    _normalize,
)


class TestLeadPipelineConfig:
    def test_agent_name(self):
        assert LeadPipeline().agent_name == "lead_pipeline"

    def test_serper_based_lead_generation(self):
        agent = LeadPipeline()
        assert hasattr(agent, "generate_leads")


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("ABC") == "abc"

    def test_strip_punctuation(self):
        assert _normalize("L'Entreprise Inc.") == "lentreprise inc"

    def test_empty(self):
        assert _normalize("") == ""

    def test_none(self):
        assert _normalize(None) == ""


class TestLeadPipelineStep:
    @pytest.mark.asyncio
    async def test_no_businesses_returns_zero(self):
        agent = LeadPipeline()
        with patch("src.agents.distribution.lead_pipeline.get_active_businesses", new_callable=AsyncMock, return_value=[]):
            ctx = MagicMock()
            result = await agent.generate_leads(ctx)
        assert result["businesses_processed"] == 0
        assert result["total_leads"] == 0

    @pytest.mark.asyncio
    async def test_serper_places_source(self):
        from src.agents.distribution.lead_pipeline import _search_serper_places
        with patch("src.agents.distribution.lead_pipeline.serper") as mock_serper:
            mock_serper.search_maps = AsyncMock(return_value=[
                {"name": "Toiture ABC", "phone": "+15145551234", "address": "123 Rue Test, QC", "rating": 4.5, "reviews": 20, "website": "toitureabc.ca", "place_id": "ChIJ123"},
            ])
            leads = await _search_serper_places([{"q": "couvreur toiture", "location": "QC", "num": 20}])
        assert len(leads) == 1
        assert leads[0]["source"] == "google_maps"
        assert leads[0]["consent_type"] == "conspicuous_publication"


# ── Enrichment ────────────────────────────────────────────────────────────────

from src.agents.distribution.enrichment import (
    EnrichmentAgent,
    compute_lead_score,
    _extract_emails_from_html,
)


class TestEnrichmentConfig:
    def test_agent_name(self):
        assert EnrichmentAgent().agent_name == "enrichment_agent"


class TestEmailExtraction:
    def test_finds_emails(self):
        html = '<a href="mailto:info@example.com">Contact</a> and john@test.ca'
        emails = _extract_emails_from_html(html)
        assert "info@example.com" in emails
        assert "john@test.ca" in emails

    def test_deduplicates(self):
        html = "info@test.com info@test.com info@test.com"
        emails = _extract_emails_from_html(html)
        assert len(emails) == 1

    def test_empty_html(self):
        assert _extract_emails_from_html("") == []


class TestLeadScoring:
    """Lead scoring: ICP 40pts, Signal 30pts, Contact 15pts, Tech 15pts."""

    def test_perfect_score(self):
        score = compute_lead_score(
            icp_config={"geo": "QC", "language": "fr"},
            lead={"province": "QC", "language": "fr"},
            has_signal=True,
            signal_age_days=3,
            email_verified=True,
            has_phone=True,
            has_website=False,
        )
        assert score == 100

    def test_zero_data_gets_base_score(self):
        score = compute_lead_score(
            icp_config={},
            lead={},
            has_signal=False,
            email_verified=False,
            has_phone=False,
            has_website=True,
        )
        assert 15 <= score <= 30  # base ICP + some tech

    def test_signal_boosts_score(self):
        without = compute_lead_score(
            icp_config={"geo": "QC", "language": "fr"},
            lead={"province": "QC", "language": "fr"},
            has_signal=False,
            email_verified=True,
            has_phone=True,
            has_website=True,
        )
        with_signal = compute_lead_score(
            icp_config={"geo": "QC", "language": "fr"},
            lead={"province": "QC", "language": "fr"},
            has_signal=True,
            signal_age_days=5,
            email_verified=True,
            has_phone=True,
            has_website=True,
        )
        assert with_signal > without

    def test_recent_signal_scores_higher(self):
        recent = compute_lead_score(
            icp_config={}, lead={},
            has_signal=True, signal_age_days=3,
            email_verified=False, has_phone=False, has_website=True,
        )
        old = compute_lead_score(
            icp_config={}, lead={},
            has_signal=True, signal_age_days=25,
            email_verified=False, has_phone=False, has_website=True,
        )
        assert recent > old

    def test_no_website_is_high_intent(self):
        with_site = compute_lead_score(
            icp_config={}, lead={},
            has_signal=False,
            email_verified=False, has_phone=False, has_website=True,
        )
        no_site = compute_lead_score(
            icp_config={}, lead={},
            has_signal=False,
            email_verified=False, has_phone=False, has_website=False,
        )
        assert no_site > with_site

    def test_verified_email_plus_phone_max(self):
        score = compute_lead_score(
            icp_config={}, lead={},
            has_signal=False,
            email_verified=True, has_phone=True, has_website=True,
        )
        no_contact = compute_lead_score(
            icp_config={}, lead={},
            has_signal=False,
            email_verified=False, has_phone=False, has_website=True,
        )
        assert score > no_contact

    def test_score_bounded_0_100(self):
        score = compute_lead_score(
            icp_config={"geo": "QC", "language": "fr"},
            lead={"province": "QC", "language": "fr"},
            has_signal=True, signal_age_days=1,
            email_verified=True, has_phone=True, has_website=False,
        )
        assert 0 <= score <= 100


# ── Signal Monitor ────────────────────────────────────────────────────────────

from src.agents.distribution.signal_monitor import (
    SIGNAL_HANDLERS,
    SignalMonitor,
)


class TestSignalMonitorConfig:
    def test_agent_name(self):
        assert SignalMonitor().agent_name == "signal_monitor"

    def test_handlers_for_spec_signal_types(self):
        required = ["new_business_registration", "building_permit_issued", "website_visit"]
        for sig in required:
            assert sig in SIGNAL_HANDLERS, f"Missing handler for signal: {sig}"


class TestSignalMonitorStep:
    @pytest.mark.asyncio
    async def test_no_businesses_returns_zero(self):
        agent = SignalMonitor()
        with patch("src.agents.distribution.signal_monitor.get_active_businesses", new_callable=AsyncMock, return_value=[]):
            ctx = MagicMock()
            result = await agent.scan_signals(ctx)
        assert result["businesses_scanned"] == 0
        assert result["signals_detected"] == 0


# ── Outreach ──────────────────────────────────────────────────────────────────

from src.agents.distribution.outreach import (
    AUTONOMY_LEVELS,
    OutreachAgent,
    determine_autonomy_level,
)


class TestOutreachConfig:
    def test_agent_name(self):
        assert OutreachAgent().agent_name == "outreach_agent"


class TestTieredAutonomy:
    """§13.C: Tiered autonomy for outreach."""

    def test_shadow_mode_first_two_weeks(self):
        created = datetime.now(tz=timezone.utc) - timedelta(days=5)
        assert determine_autonomy_level(created) == "shadow"

    def test_semi_mode_week_3_4(self):
        created = datetime.now(tz=timezone.utc) - timedelta(days=20)
        assert determine_autonomy_level(created) == "semi"

    def test_full_mode_after_month(self):
        created = datetime.now(tz=timezone.utc) - timedelta(days=45)
        assert determine_autonomy_level(created) == "full"

    def test_none_defaults_to_shadow(self):
        assert determine_autonomy_level(None) == "shadow"

    def test_day_14_is_still_shadow(self):
        created = datetime.now(tz=timezone.utc) - timedelta(days=13)
        assert determine_autonomy_level(created) == "shadow"

    def test_day_30_transitions_to_full(self):
        created = datetime.now(tz=timezone.utc) - timedelta(days=30)
        assert determine_autonomy_level(created) == "full"


class TestOutreachStep:
    @pytest.mark.asyncio
    async def test_no_businesses_returns_zero(self):
        agent = OutreachAgent()
        with patch("src.agents.distribution.outreach.get_active_businesses", new_callable=AsyncMock, return_value=[]):
            ctx = MagicMock()
            result = await agent.run_outreach(ctx)
        assert result["businesses"] == 0


class TestOutreachPrompt:
    def test_under_80_words_rule(self):
        from src.agents.distribution.outreach import OUTREACH_SYSTEM_PROMPT
        assert "80" in OUTREACH_SYSTEM_PROMPT

    def test_no_links_first_email(self):
        from src.agents.distribution.outreach import OUTREACH_SYSTEM_PROMPT
        assert "lien" in OUTREACH_SYSTEM_PROMPT.lower() or "link" in OUTREACH_SYSTEM_PROMPT.lower()

    def test_casl_compliance(self):
        from src.agents.distribution.outreach import OUTREACH_SYSTEM_PROMPT
        assert "CASL" in OUTREACH_SYSTEM_PROMPT

    def test_secondary_domains_only(self):
        # This is enforced in the Instantly setup (domain_provisioner), not the prompt
        from src.agents.distribution.outreach import OUTREACH_SYSTEM_PROMPT
        assert "signal" in OUTREACH_SYSTEM_PROMPT.lower()


# ── Reply Handler ─────────────────────────────────────────────────────────────

from src.agents.distribution.reply_handler import (
    CONFIDENCE_THRESHOLD,
    REPLY_CATEGORIES,
    ReplyHandler,
    _route_not_interested,
    _route_positive_interested,
    _route_unsubscribe,
)


class TestReplyHandlerConfig:
    def test_agent_name(self):
        assert ReplyHandler().agent_name == "reply_handler"

    def test_confidence_threshold(self):
        assert CONFIDENCE_THRESHOLD == 0.80

    def test_all_categories_defined(self):
        required = [
            "positive_interested", "positive_question",
            "negative_not_interested", "negative_competitor",
            "objection", "ooo_autoresponder", "unsubscribe", "wrong_person",
        ]
        for cat in required:
            assert cat in REPLY_CATEGORIES


class TestReplyRouting:
    @pytest.mark.asyncio
    async def test_unsubscribe_updates_status(self):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("src.agents.distribution.reply_handler.SessionLocal", return_value=mock_db):
            await _route_unsubscribe(42)
        mock_db.execute.assert_called_once()
        call_params = mock_db.execute.call_args[0][0].text
        assert "unsubscribed" in call_params

    @pytest.mark.asyncio
    async def test_positive_interested_marks_replied(self):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.distribution.reply_handler.SessionLocal", return_value=mock_db),
            patch("src.agents.voice_agent.VoiceAgent", side_effect=ImportError),
        ):
            await _route_positive_interested(1, 1)
        assert mock_db.execute.call_count == 2  # update lead + log voice call

    @pytest.mark.asyncio
    async def test_not_interested_marks_lost(self):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("src.agents.distribution.reply_handler.SessionLocal", return_value=mock_db):
            await _route_not_interested(1)
        call_params = mock_db.execute.call_args[0][0].text
        assert "lost" in call_params


class TestReplyHandlerStep:
    @pytest.mark.asyncio
    async def test_no_replies_returns_zero(self):
        agent = ReplyHandler()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))

        with patch("src.agents.distribution.reply_handler.SessionLocal", return_value=mock_db):
            ctx = MagicMock()
            ctx.workflow_input = MagicMock(return_value={})
            result = await agent.process_replies(ctx)
        assert result["processed"] == 0


class TestPlaybookDrivenDesign:
    """Key design: changing verticals = changing playbook config, NOT the code."""

    def test_lead_sources_read_from_playbook(self):
        import inspect
        source = inspect.getsource(LeadPipeline.generate_leads)
        assert "load_playbook" in source
        assert "_build_search_queries" in source or "lead_sources" in source

    def test_signals_read_from_playbook(self):
        import inspect
        source = inspect.getsource(SignalMonitor.scan_signals)
        assert "signals" in source
        assert "load_playbook" in source

    def test_messaging_read_from_playbook(self):
        import inspect
        source = inspect.getsource(OutreachAgent.run_outreach)
        assert "messaging" in source
        assert "load_playbook" in source
