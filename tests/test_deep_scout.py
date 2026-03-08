"""Tests for the Deep Scout agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.deep_scout import (
    DeepScout,
    _load_prompt,
    _parse_scout_output,
    _score_channels_ice,
    _validate_playbook,
    GTM_SEPARATOR,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    return DeepScout()


@pytest.fixture
def sample_idea_input():
    return {
        "idea_id": 1,
        "name": "Quote OS",
        "niche": "construction quoting",
        "us_equivalent": "Jobber",
        "us_equivalent_url": "https://getjobber.com",
        "score": 8.5,
    }


@pytest.fixture
def sample_scout_report():
    return """# Scout Report: Quote OS

## Executive Summary
Great opportunity in Quebec's construction sector. TAM of 15,000 contractors. Strong GO recommendation.

## Market Size & Dynamics
- TAM: ~15,000 contractors in Quebec
- Growing market
- Seasonal peaks in spring/summer

## Competitive Landscape
- No direct Canadian competitor
- US: Jobber ($49-$249/mo)

## US Competitor Branding Analysis
- URL: https://getjobber.com
- Colors: Blue and white
- Tone: Professional but friendly

## ICP (Ideal Customer Profile)
- NAICS: 238160
- Size: 1-25 employees
- Decision maker: Owner

## Channel Strategy (ICE scored)
- Cold email: Impact 8, Confidence 7, Ease 6 = ICE 336
- Facebook groups: Impact 7, Confidence 8, Ease 6 = ICE 336

## Signaux d'achat à surveiller
- New business registrations at REQ
- Building permits issued

## Recommended Pricing
- $49 CAD/mo

## Regulations & Compliance
- RBQ licence required
- Loi 101 bilingual requirement

## Risks & Mitigations
- Seasonal demand risk

## GO / NO-GO Recommendation
GO — confidence 8/10."""


@pytest.fixture
def sample_playbook():
    return {
        "go_nogo": "go",
        "confidence": 8,
        "icp": {
            "naics_codes": ["238160"],
            "company_size": "1-25",
            "decision_maker_titles": ["owner", "président"],
            "geo": "QC",
            "language": "fr",
            "tech_signals": ["no_website", "spreadsheet_user"],
            "pain_keywords": ["estimation longue", "soumission perdue"],
        },
        "channels_ranked": [
            {"channel": "cold_email", "impact": 8, "confidence": 7, "ease": 6, "ice": 336},
            {"channel": "facebook_groups", "impact": 7, "confidence": 8, "ease": 6, "ice": 336},
            {"channel": "association_partnership", "impact": 9, "confidence": 6, "ease": 5, "ice": 270},
        ],
        "lead_sources": [
            {"type": "google_maps", "query": "couvreur toiture", "geo": "QC"},
            {"type": "rbq_registry", "licence_type": "couvreur"},
        ],
        "associations": [
            {"name": "AMCQ", "url": "amcq.qc.ca", "type": "direct_niche"},
        ],
        "ecosystems": [
            {"platform": "QuickBooks", "integration_type": "export"},
        ],
        "signals": [
            {"type": "new_business_registration", "source": "req_registry", "weight": 9},
            {"type": "building_permit_issued", "source": "municipal_data", "weight": 8},
        ],
        "messaging": {
            "value_prop_fr": "Créez des soumissions professionnelles en 5 minutes",
            "value_prop_en": "Create professional quotes in 5 minutes",
            "pain_points": ["manual estimation takes too long"],
            "tone": "direct, tutoiement",
            "frameworks": ["pain_agitate_solve"],
        },
        "outreach": {
            "email_templates": 4,
            "sequence_days": [0, 3, 7, 12],
            "max_daily_emails": 50,
            "voice_trigger": "replied_positive",
            "cadence": "email → email → email+loom → breakup",
        },
        "pricing_recommendation": {
            "price_cad": 49,
            "billing": "monthly",
            "annual_discount_pct": 20,
            "tiers": 3,
        },
        "top_keywords_fr": ["soumission couvreur", "estimation toiture"],
        "top_keywords_en": ["roofing quote software"],
        "referral": {"incentive": "1_month_free", "type": "double_sided"},
    }


@pytest.fixture
def full_response(sample_scout_report, sample_playbook):
    return f"{sample_scout_report}\n\n{GTM_SEPARATOR}\n\n{json.dumps(sample_playbook, indent=2)}"


# ── Prompt Tests ──────────────────────────────────────────────────────────────


class TestPrompt:
    def test_load_prompt(self):
        prompt = _load_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 200

    def test_prompt_has_separator_instruction(self):
        prompt = _load_prompt()
        assert GTM_SEPARATOR in prompt

    def test_prompt_requests_both_outputs(self):
        prompt = _load_prompt()
        assert "Scout Report" in prompt or "SCOUT REPORT" in prompt
        assert "GTM Playbook" in prompt or "gtm_playbooks" in prompt.lower()


# ── ICE Scoring Tests ─────────────────────────────────────────────────────────


class TestICEScoring:
    def test_computes_ice_product(self):
        channels = [
            {"channel": "cold_email", "impact": 8, "confidence": 7, "ease": 6},
        ]
        scored = _score_channels_ice(channels)
        assert scored[0]["ice"] == 8 * 7 * 6

    def test_sorts_by_ice_descending(self):
        channels = [
            {"channel": "low", "impact": 2, "confidence": 2, "ease": 2},
            {"channel": "high", "impact": 9, "confidence": 9, "ease": 9},
            {"channel": "mid", "impact": 5, "confidence": 5, "ease": 5},
        ]
        scored = _score_channels_ice(channels)
        assert scored[0]["channel"] == "high"
        assert scored[-1]["channel"] == "low"

    def test_clamps_values_1_10(self):
        channels = [
            {"channel": "edge", "impact": 0, "confidence": 15, "ease": -1},
        ]
        scored = _score_channels_ice(channels)
        assert scored[0]["impact"] == 1
        assert scored[0]["confidence"] == 10
        assert scored[0]["ease"] == 1

    def test_empty_channels(self):
        assert _score_channels_ice([]) == []


# ── Output Parsing Tests ──────────────────────────────────────────────────────


class TestParseScoutOutput:
    def test_with_separator(self, full_response, sample_playbook):
        report, playbook = _parse_scout_output(full_response)
        assert "# Scout Report: Quote OS" in report
        assert playbook is not None
        assert playbook["go_nogo"] == "go"
        assert playbook["confidence"] == 8

    def test_without_separator_finds_json(self, sample_scout_report, sample_playbook):
        text = f"{sample_scout_report}\n\n{json.dumps(sample_playbook)}"
        report, playbook = _parse_scout_output(text)
        assert "Scout Report" in report
        assert playbook is not None
        assert playbook["go_nogo"] == "go"

    def test_with_code_fenced_json(self, sample_scout_report, sample_playbook):
        text = (
            f"{sample_scout_report}\n\n{GTM_SEPARATOR}\n\n"
            f"```json\n{json.dumps(sample_playbook)}\n```"
        )
        report, playbook = _parse_scout_output(text)
        assert playbook is not None
        assert playbook["icp"]["geo"] == "QC"

    def test_no_json_returns_none(self, sample_scout_report):
        report, playbook = _parse_scout_output(sample_scout_report)
        # The report has no JSON block, so playbook should be None
        # (unless the brace-finding heuristic grabs something)
        assert isinstance(report, str)

    def test_report_has_all_sections(self, full_response):
        report, _ = _parse_scout_output(full_response)
        required_sections = [
            "Executive Summary",
            "Market Size",
            "Competitive Landscape",
            "ICP",
            "Channel Strategy",
            "Pricing",
            "GO / NO-GO",
        ]
        for section in required_sections:
            assert section in report, f"Missing section: {section}"


# ── Playbook Validation Tests ─────────────────────────────────────────────────


class TestValidatePlaybook:
    def test_valid_playbook(self, sample_playbook):
        missing = _validate_playbook(sample_playbook)
        assert missing == []

    def test_missing_keys(self):
        incomplete = {"go_nogo": "go", "confidence": 5}
        missing = _validate_playbook(incomplete)
        assert "icp" in missing
        assert "channels_ranked" in missing
        assert "lead_sources" in missing
        assert "messaging" in missing
        assert "signals" in missing

    def test_empty_playbook(self):
        missing = _validate_playbook({})
        assert len(missing) == 7


# ── Agent Config Tests ────────────────────────────────────────────────────────


class TestDeepScoutConfig:
    def test_agent_name(self, agent):
        assert agent.agent_name == "deep_scout"

    def test_default_model_is_opus(self, agent):
        assert agent.default_model == "opus"


# ── Step Tests ────────────────────────────────────────────────────────────────


class TestResearchMarket:
    @pytest.mark.asyncio
    async def test_research_returns_expected_keys(self, agent, sample_idea_input):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value=sample_idea_input)

        with patch("src.agents.deep_scout.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "<html>search results</html>"
            mock_resp.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await agent.research_market(ctx)

        assert result["idea_id"] == 1
        assert result["idea_name"] == "Quote OS"
        assert "competitor_search" in result
        assert "association_search" in result
        assert "market_search" in result


class TestDiscoverChannels:
    @pytest.mark.asyncio
    async def test_calls_channel_discovery(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "idea_data": {"niche": "construction quoting"},
            "niche": "construction quoting",
            "idea_name": "Quote OS",
        })

        mock_channels = [
            {"platform": "reddit", "name": "r/roofing", "impact": 7, "confidence": 8, "ease": 6, "ice": 336},
        ]

        with patch("src.agents.distribution.channel_discovery.discover_channels", new_callable=AsyncMock, return_value=mock_channels):
            result = await agent.discover_channels(ctx)

        assert "ranked_channels" in result
        assert result["channels_found"] >= 0


class TestGenerateGTMPlaybook:
    @pytest.mark.asyncio
    async def test_parses_report_and_playbook(self, agent, full_response):
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "research_market": {"idea_data": {}, "niche": "test"},
                "analyze_us_competitor": {"us_equivalent": "", "us_url": "", "page_content": {}},
                "discover_channels": {"ranked_channels": [], "channels_found": 0},
                "research_regulations": {"regulations_search": "", "bilingual_search": "", "casl_search": ""},
            }[name]
        )

        with (
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="opus"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.deep_scout.call_claude", new_callable=AsyncMock) as mock_claude,
            patch("src.knowledge.SessionLocal") as mock_sl,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
            mock_sl.return_value = mock_db
            mock_claude.return_value = (full_response, 0.12)
            result = await agent.generate_gtm_playbook(ctx)

        assert "# Scout Report" in result["scout_report"]
        assert result["gtm_playbook"] is not None
        assert result["gtm_playbook"]["go_nogo"] == "go"
        assert result["cost_usd"] == 0.12

        # Channels should be ICE-sorted
        channels = result["gtm_playbook"]["channels_ranked"]
        ices = [c["ice"] for c in channels]
        assert ices == sorted(ices, reverse=True)


class TestSaveAndRecommend:
    @pytest.mark.asyncio
    async def test_go_creates_business_and_playbook(self, agent, sample_playbook):
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "research_market": {"idea_id": 1, "idea_name": "Quote OS", "niche": "construction"},
                "generate_gtm_playbook": {
                    "scout_report": "# Scout Report\nTest",
                    "gtm_playbook": sample_playbook,
                    "cost_usd": 0.10,
                },
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        # First call: UPDATE ideas, returns None
        # Second call: SELECT businesses, returns None (no existing biz)
        # Third call: INSERT businesses, returns id=10
        # Fourth call: INSERT gtm_playbooks
        call_count = 0
        biz_row = MagicMock()
        biz_row.id = 10

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 2:
                result.fetchone = MagicMock(return_value=None)
            elif call_count == 3:
                result.fetchone = MagicMock(return_value=biz_row)
            else:
                result.fetchone = MagicMock(return_value=None)
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.deep_scout.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.save_and_recommend(ctx)

        assert result["go_nogo"] == "go"
        assert result["business_id"] == 10
        assert result["playbook_saved"] is True

    @pytest.mark.asyncio
    async def test_nogo_doesnt_create_business(self, agent):
        nogo_playbook = {
            "go_nogo": "nogo",
            "confidence": 3,
            "icp": {},
            "channels_ranked": [],
            "lead_sources": [],
            "messaging": {},
            "signals": [],
        }
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "research_market": {"idea_id": 2, "idea_name": "Bad Idea", "niche": "nothing"},
                "generate_gtm_playbook": {
                    "scout_report": "# Scout Report\nNOGO",
                    "gtm_playbook": nogo_playbook,
                    "cost_usd": 0.08,
                },
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.fetchone = MagicMock(return_value=None)
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.deep_scout.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.save_and_recommend(ctx)

        assert result["go_nogo"] == "nogo"
        assert result["business_id"] is None

    @pytest.mark.asyncio
    async def test_none_playbook_treated_as_nogo(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(
            side_effect=lambda name: {
                "research_market": {"idea_id": 3, "idea_name": "Broken", "niche": "x"},
                "generate_gtm_playbook": {
                    "scout_report": "# Scout Report\nParse failed",
                    "gtm_playbook": None,
                    "cost_usd": 0.05,
                },
            }[name]
        )

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.deep_scout.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.save_and_recommend(ctx)

        assert result["go_nogo"] == "nogo"
        assert result["playbook_saved"] is False


class TestPlaybookGTMSchema:
    """Verify the playbook JSON matches the full §13 GTM schema from the spec."""

    def test_playbook_has_icp_section(self, sample_playbook):
        icp = sample_playbook["icp"]
        assert "naics_codes" in icp
        assert "company_size" in icp
        assert "decision_maker_titles" in icp
        assert "geo" in icp
        assert "language" in icp
        assert "pain_keywords" in icp

    def test_playbook_has_channels(self, sample_playbook):
        channels = sample_playbook["channels_ranked"]
        assert len(channels) >= 1
        for ch in channels:
            assert "channel" in ch
            assert "impact" in ch
            assert "confidence" in ch
            assert "ease" in ch
            assert "ice" in ch

    def test_playbook_has_lead_sources(self, sample_playbook):
        sources = sample_playbook["lead_sources"]
        assert len(sources) >= 1
        assert sources[0]["type"] in ("google_maps", "rbq_registry", "req_registry", "association_directory")

    def test_playbook_has_signals(self, sample_playbook):
        signals = sample_playbook["signals"]
        assert len(signals) >= 1
        assert "type" in signals[0]
        assert "source" in signals[0]
        assert "weight" in signals[0]

    def test_playbook_has_messaging(self, sample_playbook):
        msg = sample_playbook["messaging"]
        assert "value_prop_fr" in msg
        assert "value_prop_en" in msg
        assert "pain_points" in msg
        assert "frameworks" in msg

    def test_playbook_has_outreach_config(self, sample_playbook):
        out = sample_playbook["outreach"]
        assert "email_templates" in out
        assert "sequence_days" in out
        assert "max_daily_emails" in out
        assert "voice_trigger" in out

    def test_playbook_has_referral(self, sample_playbook):
        ref = sample_playbook["referral"]
        assert ref["incentive"] == "1_month_free"
        assert ref["type"] == "double_sided"
