"""Tests for the Domain Provisioner agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.domain_provisioner import (
    COLD_EMAIL_TLDS,
    PROVINCE_AREA_CODES,
    DomainProvisioner,
    _slug_to_domain_base,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    return DomainProvisioner()


@pytest.fixture
def workflow_input():
    return {
        "business_id": 1,
        "name": "Toîturo",
        "slug": "toituro",
        "domain": None,
        "province": "QC",
        "pricing": {"pro_price_cad": 49, "business_price_cad": 99},
    }


# ── Utility Tests ─────────────────────────────────────────────────────────────


class TestSlugNormalization:
    def test_basic(self):
        assert _slug_to_domain_base("toituro") == "toituro"

    def test_underscores(self):
        assert _slug_to_domain_base("my_app") == "myapp"

    def test_dashes(self):
        assert _slug_to_domain_base("my-app") == "myapp"

    def test_spaces(self):
        assert _slug_to_domain_base("my app") == "myapp"


class TestConfig:
    def test_cold_email_tlds(self):
        assert ".io" in COLD_EMAIL_TLDS
        assert ".co" in COLD_EMAIL_TLDS
        assert ".ca" not in COLD_EMAIL_TLDS  # NEVER cold email from .ca

    def test_quebec_area_code(self):
        assert PROVINCE_AREA_CODES["QC"] == "514"

    def test_agent_name(self, agent):
        assert agent.agent_name == "domain_provisioner"


# ── Step Tests ────────────────────────────────────────────────────────────────


class TestBuyPrimaryDomain:
    @pytest.mark.asyncio
    async def test_prefers_ca(self, agent, workflow_input):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value=workflow_input)

        with (
            patch("src.agents.domain_provisioner.namecheap") as mock_nc,
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            mock_nc.check_domain = AsyncMock(return_value={"domain": "toituro.ca", "available": True})
            mock_nc.purchase_domain = AsyncMock(return_value={
                "domain": "toituro.ca", "success": True, "order_id": "12345",
            })

            result = await agent.buy_primary_domain(ctx)

        assert result["primary_domain"] == "toituro.ca"
        assert result["purchase_success"] is True

    @pytest.mark.asyncio
    async def test_falls_back_to_com(self, agent, workflow_input):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value=workflow_input)

        with (
            patch("src.agents.domain_provisioner.namecheap") as mock_nc,
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            mock_nc.check_domain = AsyncMock(
                side_effect=[
                    {"domain": "toituro.ca", "available": False},
                    {"domain": "toituro.com", "available": True},
                ]
            )
            mock_nc.purchase_domain = AsyncMock(return_value={
                "domain": "toituro.com", "success": True, "order_id": "12346",
            })

            result = await agent.buy_primary_domain(ctx)

        assert result["primary_domain"] == "toituro.com"

    @pytest.mark.asyncio
    async def test_uses_preferred_domain(self, agent, workflow_input):
        workflow_input["domain"] = "couvrix.ca"
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value=workflow_input)

        with (
            patch("src.agents.domain_provisioner.namecheap") as mock_nc,
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            mock_nc.purchase_domain = AsyncMock(return_value={
                "domain": "couvrix.ca", "success": True, "order_id": "12347",
            })
            result = await agent.buy_primary_domain(ctx)

        assert result["primary_domain"] == "couvrix.ca"


class TestBuyColdEmailDomains:
    @pytest.mark.asyncio
    async def test_buys_secondary_tlds(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "slug": "toituro",
            "business_id": 1,
            "primary_domain": "toituro.ca",
        })

        with (
            patch("src.agents.domain_provisioner.namecheap") as mock_nc,
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            mock_nc.check_domain = AsyncMock(return_value={"available": True})
            mock_nc.purchase_domain = AsyncMock(return_value={"success": True, "order_id": "111"})

            result = await agent.buy_cold_email_domains(ctx)

        assert len(result["cold_email_domains"]) == 2
        assert "toituro.io" in result["cold_email_domains"]
        assert "toituro.co" in result["cold_email_domains"]
        # Primary .ca must NOT be in cold email domains
        assert "toituro.ca" not in result["cold_email_domains"]

    @pytest.mark.asyncio
    async def test_handles_unavailable(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "slug": "toituro",
            "business_id": 1,
            "primary_domain": "toituro.ca",
        })

        with (
            patch("src.agents.domain_provisioner.namecheap") as mock_nc,
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            mock_nc.check_domain = AsyncMock(
                side_effect=[
                    {"available": False},  # .io unavailable
                    {"available": True},   # .co available
                ]
            )
            mock_nc.purchase_domain = AsyncMock(return_value={"success": True, "order_id": "222"})

            result = await agent.buy_cold_email_domains(ctx)

        assert len(result["cold_email_domains"]) == 1
        assert "toituro.co" in result["cold_email_domains"]


class TestSetupDNS:
    @pytest.mark.asyncio
    async def test_creates_zones_for_all_domains(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "buy_primary_domain": {"primary_domain": "toituro.ca", "business_id": 1},
                "buy_cold_email_domains": {"cold_email_domains": ["toituro.io", "toituro.co"]},
            }[name]
        )

        with (
            patch("src.agents.domain_provisioner.cloudflare") as mock_cf,
            patch("src.agents.domain_provisioner.namecheap") as mock_nc,
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            mock_cf.create_zone = AsyncMock(return_value={
                "zone_id": "zone123", "nameservers": ["ns1.cf.com", "ns2.cf.com"], "success": True,
            })
            mock_cf.setup_email_dns = AsyncMock(return_value=[{"success": True}])
            mock_cf.setup_vercel_dns = AsyncMock(return_value=[{"success": True}])
            mock_nc.set_nameservers = AsyncMock(return_value={"success": True})

            result = await agent.setup_dns_all_domains(ctx)

        assert len(result["dns_results"]) == 3
        assert result["dns_results"]["toituro.ca"]["success"] is True
        assert result["primary_zone_id"] == "zone123"


class TestSetupStripe:
    @pytest.mark.asyncio
    async def test_creates_products(self, agent, workflow_input):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "slug": "toituro",
            "business_id": 1,
            "primary_domain": "toituro.ca",
        })
        ctx.workflow_input = MagicMock(return_value=workflow_input)

        with (
            patch("src.agents.domain_provisioner.stripe_setup") as mock_stripe,
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            mock_stripe.create_business_products = AsyncMock(return_value={
                "products": {"free": "prod_1", "pro": "prod_2", "business": "prod_3"},
                "prices": {
                    "free_monthly": "price_1",
                    "pro_monthly": "price_2", "pro_annual": "price_3",
                    "business_monthly": "price_4", "business_annual": "price_5",
                },
                "trial_config": {"trial_days": 14, "trial_price_id": "price_2"},
            })

            result = await agent.setup_stripe(ctx)

        assert len(result["stripe_config"]["products"]) == 3
        assert result["stripe_config"]["trial_config"]["trial_days"] == 14


class TestSetupInstantly:
    @pytest.mark.asyncio
    async def test_adds_cold_email_accounts(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "cold_email_domains": ["toituro.io", "toituro.co"],
        })

        with patch("src.agents.domain_provisioner.instantly") as mock_inst:
            mock_inst.add_sending_account = AsyncMock(return_value={
                "email": "hello@toituro.io", "success": True, "warmup_enabled": True,
            })
            result = await agent.setup_instantly(ctx)

        assert result["warmup_started"] is True
        assert len(result["instantly_accounts"]) == 2

    @pytest.mark.asyncio
    async def test_no_cold_domains_no_accounts(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={"cold_email_domains": []})

        result = await agent.setup_instantly(ctx)
        assert result["warmup_started"] is False
        assert len(result["instantly_accounts"]) == 0


class TestSaveInfra:
    @pytest.mark.asyncio
    async def test_saves_all_infra_ids(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "buy_primary_domain": {"primary_domain": "toituro.ca", "business_id": 1, "slug": "toituro"},
                "buy_cold_email_domains": {"cold_email_domains": ["toituro.io"]},
                "setup_dns_all_domains": {"dns_results": {}, "primary_zone_id": "zone1"},
                "create_vercel_project": {"vercel_project_id": "vercel1", "success": True},
                "create_github_repo": {"github_repo": "user/toituro", "success": True},
                "create_supabase_project": {"supabase_project_id": "supa1", "supabase_url": "https://supa1.supabase.co", "supabase_anon_key": "key1"},
                "setup_stripe": {"stripe_config": {}},
                "buy_twilio_number": {"phone_number": "+15145551234"},
                "create_retell_agents": {"retell_agents": [{"language": "fr", "agent_id": "ra1"}]},
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.domain_provisioner.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.save_infra_to_db(ctx)

        assert result["saved"] is True
        assert result["business_id"] == 1
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_business_id(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "buy_primary_domain": {"primary_domain": "x.ca", "business_id": None, "slug": "x"},
                "buy_cold_email_domains": {"cold_email_domains": []},
                "setup_dns_all_domains": {"dns_results": {}, "primary_zone_id": None},
                "create_vercel_project": {"vercel_project_id": None},
                "create_github_repo": {"github_repo": None},
                "create_supabase_project": {"supabase_project_id": None, "supabase_url": None, "supabase_anon_key": None},
                "setup_stripe": {"stripe_config": {}},
                "buy_twilio_number": {"phone_number": None},
                "create_retell_agents": {"retell_agents": []},
            }[name]
        )

        result = await agent.save_infra_to_db(ctx)
        assert result["saved"] is False


class TestColdEmailDomainSeparation:
    """Spec is explicit: NEVER send cold email from the primary .ca domain."""

    def test_cold_tlds_exclude_ca(self):
        assert ".ca" not in COLD_EMAIL_TLDS

    def test_cold_tlds_exclude_com(self):
        assert ".com" not in COLD_EMAIL_TLDS

    @pytest.mark.asyncio
    async def test_cold_domains_are_separate_from_primary(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "slug": "testbiz",
            "business_id": 1,
            "primary_domain": "testbiz.ca",
        })

        with (
            patch("src.agents.domain_provisioner.namecheap") as mock_nc,
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            mock_nc.check_domain = AsyncMock(return_value={"available": True})
            mock_nc.purchase_domain = AsyncMock(return_value={"success": True, "order_id": "x"})

            result = await agent.buy_cold_email_domains(ctx)

        for d in result["cold_email_domains"]:
            assert not d.endswith(".ca"), f"Cold email domain {d} uses .ca — SPEC VIOLATION"
            assert not d.endswith(".com"), f"Cold email domain {d} uses .com"
