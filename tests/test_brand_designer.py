"""Tests for the Brand Designer agent."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.brand_designer import (
    BrandDesigner,
    _generate_domain_variants,
    _load_prompt,
    _parse_brand_kit,
    _validate_brand_kit,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    return BrandDesigner()


@pytest.fixture
def sample_brand_kit():
    return {
        "name_options": [
            {"name": "Toîturo", "domain_ca": "available", "domain_com": "taken", "rationale": "Plays on toiture (roof)"},
            {"name": "Couvrix", "domain_ca": "available", "domain_com": "available", "rationale": "From couvreur"},
        ],
        "recommended_name": "Toîturo",
        "colors": {
            "primary": "#1B4D72",
            "secondary": "#F5A623",
            "accent": "#E74C3C",
            "background_light": "#FAFBFC",
            "background_dark": "#1A1A2E",
            "text_primary": "#1A1A2E",
            "text_secondary": "#6B7280",
            "success": "#10B981",
            "warning": "#F59E0B",
            "error": "#EF4444",
        },
        "typography": {
            "heading": "Plus Jakarta Sans",
            "body": "Manrope",
            "mono": "JetBrains Mono",
        },
        "tone": {
            "fr": {
                "formality": "tu",
                "headline_example": "Fais tes soumissions en 5 minutes",
                "cta_example": "Essaie gratuitement",
                "error_message_example": "Oups, quelque chose a mal tourné",
            },
            "en": {
                "headline_example": "Create quotes in 5 minutes",
                "cta_example": "Try it free",
                "error_message_example": "Oops, something went wrong",
            },
        },
        "mood_board_urls": ["https://dribbble.com/example1", "https://dribbble.com/example2"],
        "canadian_identity": {
            "tagline_fr": "Conçu au Québec",
            "tagline_en": "Made in Canada",
            "subtle_elements": "Maple leaf micro-icon in footer",
        },
        "competitor_inspiration": {
            "borrow": ["Clean pricing page layout", "Feature comparison table"],
            "avoid": ["Purple gradient hero", "Stock photos of construction"],
        },
        "logo_concept": "Toîturo in Plus Jakarta Sans Bold with accent-colored î circumflex",
    }


# ── Prompt Tests ──────────────────────────────────────────────────────────────


class TestPrompt:
    def test_loads(self):
        prompt = _load_prompt()
        assert len(prompt) > 100

    def test_has_json_schema(self):
        prompt = _load_prompt()
        assert "colors" in prompt
        assert "typography" in prompt
        assert "tone" in prompt

    def test_has_naming_rules(self):
        prompt = _load_prompt()
        assert "3 syllabes" in prompt
        assert "-ly" in prompt


# ── Parser Tests ──────────────────────────────────────────────────────────────


class TestParseBrandKit:
    def test_valid_json(self, sample_brand_kit):
        kit = _parse_brand_kit(json.dumps(sample_brand_kit))
        assert kit is not None
        assert kit["recommended_name"] == "Toîturo"

    def test_code_fenced_json(self, sample_brand_kit):
        text = f"```json\n{json.dumps(sample_brand_kit)}\n```"
        kit = _parse_brand_kit(text)
        assert kit is not None

    def test_json_with_preamble(self, sample_brand_kit):
        text = f"Here is the brand kit:\n\n{json.dumps(sample_brand_kit)}"
        kit = _parse_brand_kit(text)
        assert kit is not None

    def test_invalid_returns_none(self):
        assert _parse_brand_kit("not json at all") is None

    def test_empty_returns_none(self):
        assert _parse_brand_kit("") is None


class TestValidateBrandKit:
    def test_valid(self, sample_brand_kit):
        assert _validate_brand_kit(sample_brand_kit) == []

    def test_missing_colors(self):
        missing = _validate_brand_kit({"typography": {}, "tone": {}})
        assert "colors" in missing

    def test_empty(self):
        missing = _validate_brand_kit({})
        assert len(missing) == 3


# ── Domain Variant Tests ─────────────────────────────────────────────────────


class TestDomainVariants:
    def test_generates_4_tlds(self):
        variants = _generate_domain_variants("Toîturo")
        assert len(variants) == 4
        assert "toituro.ca" in variants
        assert "toituro.com" in variants
        assert "toituro.io" in variants
        assert "toituro.co" in variants

    def test_handles_spaces(self):
        variants = _generate_domain_variants("My App")
        assert "myapp.ca" in variants

    def test_handles_accents(self):
        variants = _generate_domain_variants("Réno Pro")
        assert "renopro.ca" in variants


# ── Agent Config Tests ────────────────────────────────────────────────────────


class TestBrandDesignerConfig:
    def test_agent_name(self, agent):
        assert agent.agent_name == "brand_designer"

    def test_default_model_is_opus(self, agent):
        assert agent.default_model == "opus"


# ── Light Mode Tests ──────────────────────────────────────────────────────────


class TestLightMode:
    @pytest.mark.asyncio
    async def test_quick_brand_returns_kit(self, agent, sample_brand_kit):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={
            "business_id": 1,
            "scout_report": "# Scout Report\nUS competitor uses blue.",
            "niche": "construction quoting",
        })

        with (
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="opus"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.brand_designer.call_claude", new_callable=AsyncMock) as mock_claude,
            patch("src.agents.brand_designer.namecheap") as mock_nc,
            patch("src.agents.brand_designer.SessionLocal") as mock_session_cls,
        ):
            mock_claude.return_value = (json.dumps(sample_brand_kit), 0.08)
            mock_nc.check_domains_batch = AsyncMock(return_value=[
                {"domain": "toituro.ca", "available": True},
                {"domain": "toituro.com", "available": False},
                {"domain": "toituro.io", "available": True},
                {"domain": "toituro.co", "available": True},
                {"domain": "couvrix.ca", "available": True},
                {"domain": "couvrix.com", "available": True},
                {"domain": "couvrix.io", "available": True},
                {"domain": "couvrix.co", "available": True},
            ])
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.execute = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_session_cls.return_value = mock_db

            result = await agent.quick_brand(ctx)

        assert result["mode"] == "light"
        assert result["brand_kit"] is not None
        kit = result["brand_kit"]
        assert kit["name_options"][0]["domain_ca"] == "available"
        assert kit["name_options"][0]["domain_com"] == "taken"


# ── Full Mode Tests ───────────────────────────────────────────────────────────


class TestFullMode:
    @pytest.mark.asyncio
    async def test_generate_brand_kit_calls_opus(self, agent, sample_brand_kit):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={"business_id": 1})
        ctx.step_output = MagicMock(return_value={
            "niche": "construction",
            "scout_report_excerpt": "test",
            "inspiration_pages": {},
        })

        with (
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="opus"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.brand_designer.call_claude", new_callable=AsyncMock) as mock_claude,
        ):
            mock_claude.return_value = (json.dumps(sample_brand_kit), 0.10)
            result = await agent.generate_brand_kit(ctx)

        assert result["brand_kit"] is not None
        assert result["brand_kit"]["recommended_name"] == "Toîturo"

    @pytest.mark.asyncio
    async def test_save_brand_kit_persists(self, agent, sample_brand_kit):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={"business_id": 1})
        ctx.step_output = MagicMock(return_value={"brand_kit": sample_brand_kit, "domain_results": []})

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.brand_designer.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.save_brand_kit(ctx)

        assert result["saved"] is True
        assert result["mode"] == "full"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_no_kit(self, agent):
        ctx = MagicMock()
        ctx.workflow_input = MagicMock(return_value={"business_id": 1})
        ctx.step_output = MagicMock(return_value={"brand_kit": None, "domain_results": []})

        result = await agent.save_brand_kit(ctx)
        assert result["saved"] is False


class TestBrandKitSchema:
    """Validate the brand kit matches the spec schema."""

    def test_has_10_colors(self, sample_brand_kit):
        assert len(sample_brand_kit["colors"]) == 10

    def test_colors_are_hex(self, sample_brand_kit):
        for key, val in sample_brand_kit["colors"].items():
            assert val.startswith("#"), f"{key} is not hex: {val}"

    def test_typography_has_3_fonts(self, sample_brand_kit):
        assert "heading" in sample_brand_kit["typography"]
        assert "body" in sample_brand_kit["typography"]
        assert "mono" in sample_brand_kit["typography"]

    def test_tone_has_fr_and_en(self, sample_brand_kit):
        assert "fr" in sample_brand_kit["tone"]
        assert "en" in sample_brand_kit["tone"]
        assert sample_brand_kit["tone"]["fr"]["formality"] in ("tu", "vous")

    def test_has_canadian_identity(self, sample_brand_kit):
        ci = sample_brand_kit["canadian_identity"]
        assert "tagline_fr" in ci
        assert "tagline_en" in ci

    def test_no_banned_fonts(self, sample_brand_kit):
        banned = {"Inter", "Roboto", "Arial"}
        for key, font in sample_brand_kit["typography"].items():
            assert font not in banned, f"Banned font used: {font}"
