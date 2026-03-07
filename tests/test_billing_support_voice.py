"""Tests for Billing Agent, Support Agent, and Voice Agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══ BILLING AGENT ════════════════════════════════════════════════════════════

from src.agents.billing_agent import (
    CANADIAN_TAX_RATES,
    DUNNING_SEQUENCE_DAYS,
    PRE_DUNNING_DAYS,
    WEBHOOK_EVENTS,
    BillingAgent,
    get_tax_rate,
)


class TestBillingConfig:
    def test_agent_name(self):
        assert BillingAgent().agent_name == "billing_agent"

    def test_handles_all_webhook_events(self):
        required = [
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "customer.subscription.trial_will_end",
            "invoice.payment_succeeded",
            "invoice.payment_failed",
            "charge.dispute.created",
        ]
        for event in required:
            assert event in WEBHOOK_EVENTS


class TestCanadianTaxes:
    def test_quebec_taxes(self):
        rate = get_tax_rate("QC")
        assert rate["tps"] == 0.05
        assert rate["tvq"] == 0.09975
        assert abs(rate["total"] - 0.14975) < 0.001

    def test_ontario_tvh(self):
        rate = get_tax_rate("ON")
        assert rate["tvh"] == 0.13

    def test_alberta_gst_only(self):
        rate = get_tax_rate("AB")
        assert rate["total"] == 0.05

    def test_unknown_province_defaults(self):
        rate = get_tax_rate("XX")
        assert rate["total"] == 0.05  # GST only fallback


class TestPaymentRecovery:
    def test_pre_dunning_intervals(self):
        assert PRE_DUNNING_DAYS == [30, 15, 7]

    def test_dunning_sequence(self):
        assert DUNNING_SEQUENCE_DAYS == [0, 3, 7, 14]
        assert len(DUNNING_SEQUENCE_DAYS) == 4  # 4-email sequence


class TestWebhookHandling:
    @pytest.mark.asyncio
    async def test_unknown_event_not_handled(self):
        agent = BillingAgent()
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={
            "event_type": "unknown.event",
            "event_data": {},
        })
        with patch.object(agent, "log_execution", new_callable=AsyncMock):
            result = await agent.handle_webhook(ctx)
        assert result["handled"] is False

    @pytest.mark.asyncio
    async def test_sub_deleted_downgrades_not_deletes(self):
        agent = BillingAgent()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("src.agents.billing_agent.SessionLocal", return_value=mock_db):
            result = await agent._handle_sub_deleted({"id": "sub_123"})

        assert result["action"] == "downgraded_to_free"
        call_sql = mock_db.execute.call_args[0][0].text
        assert "free" in call_sql  # downgrade to free, not delete

    @pytest.mark.asyncio
    async def test_trial_ending_sends_sms(self):
        agent = BillingAgent()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        cust = MagicMock()
        cust.id = 1
        cust.name = "Jean"
        cust.email = "jean@test.com"
        cust.phone = "+15145551234"
        cust.language = "fr"
        cust.business_id = 1
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=cust)))

        with (
            patch("src.agents.billing_agent.SessionLocal", return_value=mock_db),
            patch("src.agents.billing_agent.twilio_client") as mock_twilio,
        ):
            mock_twilio.send_sms = AsyncMock(return_value={"sid": "SM123"})
            result = await agent._handle_trial_ending({"customer": "cus_123"})

        assert "sms" in result["channels"]
        mock_twilio.send_sms.assert_called_once()

    @pytest.mark.asyncio
    async def test_payment_failed_initiates_dunning(self):
        agent = BillingAgent()
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.commit = AsyncMock()

        cust = MagicMock()
        cust.id = 1
        cust.name = "Jean"
        cust.email = "jean@test.com"
        cust.phone = "+15145551234"
        cust.language = "fr"
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=cust)))

        with (
            patch("src.agents.billing_agent.SessionLocal", return_value=mock_db),
            patch("src.agents.billing_agent.twilio_client") as mock_twilio,
        ):
            mock_twilio.send_sms = AsyncMock()
            result = await agent._handle_payment_failed({"customer": "cus_123", "attempt_count": 1})

        assert result["action"] == "dunning_initiated"
        assert "sms" in result["channels"]


# ═══ SUPPORT AGENT ════════════════════════════════════════════════════════════

from src.agents.support_agent import (
    CHURN_SIGNALS,
    SupportAgent,
)


class TestSupportConfig:
    def test_agent_name(self):
        assert SupportAgent().agent_name == "support_agent"

    def test_default_model_is_sonnet(self):
        assert SupportAgent().default_model == "sonnet"

    def test_churn_signals_defined(self):
        assert "inactive_7d" in CHURN_SIGNALS
        assert "usage_drop_50" in CHURN_SIGNALS
        assert "unresolved_48h" in CHURN_SIGNALS


class TestSupportTicket:
    @pytest.mark.asyncio
    async def test_empty_message_rejected(self):
        agent = SupportAgent()
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={
            "business_id": 1, "customer_id": 1, "message": "",
        })
        result = await agent.handle_ticket(ctx)
        assert result["response"] is None

    @pytest.mark.asyncio
    async def test_responds_in_customer_language(self):
        agent = SupportAgent()
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={
            "business_id": 1, "customer_id": 1, "message": "How do I export?",
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
            result = MagicMock()
            if call_count == 1:
                result.fetchone = MagicMock(return_value=cust)
            elif call_count == 2:
                result.fetchall = MagicMock(return_value=[])
            else:
                result.fetchone = MagicMock(return_value=None)
            return result

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
        assert result["response"] is not None
        # Verify the system prompt was in French
        call_args = mock_claude.call_args[1]
        assert "français" in call_args["system"].lower()


class TestSupportPrompt:
    def test_has_language_variable(self):
        from src.agents.support_agent import SUPPORT_SYSTEM_PROMPT
        assert "{language}" in SUPPORT_SYSTEM_PROMPT

    def test_has_kb_context_variable(self):
        from src.agents.support_agent import SUPPORT_SYSTEM_PROMPT
        assert "{kb_context}" in SUPPORT_SYSTEM_PROMPT

    def test_honest_about_unknowns(self):
        from src.agents.support_agent import SUPPORT_SYSTEM_PROMPT
        assert "ne connais pas" in SUPPORT_SYSTEM_PROMPT.lower() or "don't know" in SUPPORT_SYSTEM_PROMPT.lower()


# ═══ VOICE AGENT ══════════════════════════════════════════════════════════════

from src.agents.voice_agent import (
    MAX_DAILY_CALLS,
    WARM_STATUSES,
    VoiceAgent,
)


class TestVoiceConfig:
    def test_agent_name(self):
        assert VoiceAgent().agent_name == "voice_agent"

    def test_warm_statuses(self):
        assert "replied" in WARM_STATUSES
        assert "booked" in WARM_STATUSES
        assert "trial" in WARM_STATUSES
        assert "callback_requested" in WARM_STATUSES

    def test_cold_statuses_excluded(self):
        assert "new" not in WARM_STATUSES
        assert "contacted" not in WARM_STATUSES
        assert "enriched" not in WARM_STATUSES

    def test_daily_call_limit(self):
        assert MAX_DAILY_CALLS == 30


class TestWarmCallsOnly:
    """SPEC §2: WARM CALLS ONLY. $15,000 fine per cold call."""

    @pytest.mark.asyncio
    async def test_blocks_new_lead(self):
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

    @pytest.mark.asyncio
    async def test_blocks_contacted_lead(self):
        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "phone": "+15145551234",
            "lead_status": "contacted",
            "is_customer": False,
            "province": "QC",
            "business_id": 1,
        })

        result = await agent.check_compliance(ctx)
        assert result["can_call"] is False
        assert result["gate"] == "consent"

    @pytest.mark.asyncio
    async def test_blocks_enriched_lead(self):
        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "phone": "+15145551234",
            "lead_status": "enriched",
            "is_customer": False,
            "province": "QC",
            "business_id": 1,
        })

        result = await agent.check_compliance(ctx)
        assert result["can_call"] is False

    @pytest.mark.asyncio
    async def test_allows_replied_lead(self):
        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "phone": "+15145551234",
            "lead_status": "replied",
            "is_customer": False,
            "province": "QC",
            "business_id": 1,
        })

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=MagicMock(cnt=0))))

        with (
            patch("src.agents.voice_agent.dncl_client") as mock_dncl,
            patch("src.agents.voice_agent.SessionLocal", return_value=mock_db),
        ):
            mock_dncl.check_dncl = AsyncMock(return_value={"on_dncl": False, "can_call": True})
            mock_dncl.is_within_calling_hours = MagicMock(return_value=True)
            result = await agent.check_compliance(ctx)

        assert result["can_call"] is True

    @pytest.mark.asyncio
    async def test_allows_existing_customer(self):
        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "phone": "+15145551234",
            "lead_status": None,
            "is_customer": True,
            "province": "QC",
            "business_id": 1,
        })

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=MagicMock(cnt=0))))

        with (
            patch("src.agents.voice_agent.dncl_client") as mock_dncl,
            patch("src.agents.voice_agent.SessionLocal", return_value=mock_db),
        ):
            mock_dncl.check_dncl = AsyncMock(return_value={"on_dncl": False})
            mock_dncl.is_within_calling_hours = MagicMock(return_value=True)
            result = await agent.check_compliance(ctx)

        assert result["can_call"] is True


class TestDNCLCompliance:
    @pytest.mark.asyncio
    async def test_blocks_dncl_number(self):
        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "phone": "+15145551234",
            "lead_status": "replied",
            "is_customer": False,
            "province": "QC",
            "business_id": 1,
        })

        with patch("src.agents.voice_agent.dncl_client") as mock_dncl:
            mock_dncl.check_dncl = AsyncMock(return_value={"on_dncl": True, "source": "cache"})
            result = await agent.check_compliance(ctx)

        assert result["can_call"] is False
        assert result["gate"] == "dncl"

    @pytest.mark.asyncio
    async def test_blocks_outside_calling_hours(self):
        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "phone": "+15145551234",
            "lead_status": "replied",
            "is_customer": False,
            "province": "QC",
            "business_id": 1,
        })

        with patch("src.agents.voice_agent.dncl_client") as mock_dncl:
            mock_dncl.check_dncl = AsyncMock(return_value={"on_dncl": False})
            mock_dncl.is_within_calling_hours = MagicMock(return_value=False)
            result = await agent.check_compliance(ctx)

        assert result["can_call"] is False
        assert result["gate"] == "hours"
        assert result["schedule_later"] is True

    @pytest.mark.asyncio
    async def test_blocks_no_phone(self):
        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "phone": None,
            "lead_status": "replied",
            "is_customer": False,
            "province": "QC",
            "business_id": 1,
        })
        result = await agent.check_compliance(ctx)
        assert result["can_call"] is False
        assert result["gate"] == "phone"


class TestCallingHours:
    def test_function_exists(self):
        from src.integrations.dncl_client import is_within_calling_hours
        result = is_within_calling_hours("QC")
        assert isinstance(result, bool)

    def test_phone_normalization(self):
        from src.integrations.dncl_client import _normalize_phone
        assert _normalize_phone("5145551234") == "+15145551234"
        assert _normalize_phone("15145551234") == "+15145551234"
        assert _normalize_phone("+15145551234") == "+15145551234"


class TestDoNotCallOutcome:
    """When someone says 'don't call me', add to internal DNCL IMMEDIATELY."""

    @pytest.mark.asyncio
    async def test_do_not_call_adds_to_dncl(self):
        agent = VoiceAgent()
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "make_call": {"call_made": True, "call_id": "call_123"},
                "prepare_call": {
                    "lead_id": 1, "customer_id": None, "business_id": 1,
                    "phone": "+15145551234", "call_type": "qualification",
                },
                "check_compliance": {"can_call": True},
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.voice_agent.retell_client") as mock_retell,
            patch("src.agents.voice_agent.dncl_client") as mock_dncl,
            patch("src.agents.voice_agent.SessionLocal", return_value=mock_db),
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="sonnet"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.voice_agent.call_claude", new_callable=AsyncMock) as mock_claude,
        ):
            mock_retell.get_call = AsyncMock(return_value={
                "transcript": "Please don't call me again.",
                "call_duration_ms": 15000,
            })
            mock_claude.return_value = (
                json.dumps({"outcome": "do_not_call", "summary": "Asked not to call", "sentiment_score": -0.8}),
                0.01,
            )
            mock_dncl.add_to_internal_dncl = AsyncMock()

            result = await agent.process_result(ctx)

        assert result["outcome"] == "do_not_call"
        mock_dncl.add_to_internal_dncl.assert_called_once_with("+15145551234")
