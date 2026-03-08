"""Tests for the channel discovery system (replaces SparkToro)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.distribution.channel_discovery import (
    _compute_ice,
    _score_and_rank,
    discover_channels,
)


class TestICEComputation:
    def test_basic_ice(self):
        ch = {"impact": 8, "confidence": 7, "ease": 6}
        score = _compute_ice(ch)
        assert score == 8 * 7 * 6
        assert ch["ice"] == 336

    def test_clamps_values(self):
        ch = {"impact": 0, "confidence": 15, "ease": -3}
        _compute_ice(ch)
        assert ch["impact"] == 1
        assert ch["confidence"] == 10
        assert ch["ease"] == 1


class TestScoreAndRank:
    def test_sorts_by_ice_descending(self):
        channels = [
            {"name": "low", "platform": "reddit", "impact": 2, "confidence": 2, "ease": 2},
            {"name": "high", "platform": "reddit", "impact": 9, "confidence": 9, "ease": 9},
        ]
        ranked = _score_and_rank(channels, [])
        assert ranked[0]["name"] == "high"

    def test_boosts_verified_channels(self):
        channels = [
            {"name": "ch1", "platform": "facebook", "impact": 5, "confidence": 5, "ease": 5, "_verified": True},
            {"name": "ch2", "platform": "facebook", "impact": 5, "confidence": 5, "ease": 5, "_verified": False},
        ]
        ranked = _score_and_rank(channels, [])
        verified = next(c for c in ranked if c["name"] == "ch1")
        unverified = next(c for c in ranked if c["name"] == "ch2")
        assert verified["ice"] > unverified["ice"]

    def test_adds_reddit_discoveries(self):
        claude = [{"name": "r/existing", "platform": "reddit", "impact": 7, "confidence": 7, "ease": 7}]
        reddit = [{"name": "r/newdiscovery", "platform": "reddit", "estimated_audience": "5K", "subscribers": 5000}]
        ranked = _score_and_rank(claude, reddit)
        names = [c["name"] for c in ranked]
        assert "r/newdiscovery" in names

    def test_does_not_duplicate_reddit(self):
        claude = [{"name": "r/roofing", "platform": "reddit", "impact": 7, "confidence": 7, "ease": 7}]
        reddit = [{"name": "r/roofing", "platform": "reddit", "subscribers": 5000}]
        ranked = _score_and_rank(claude, reddit)
        roofing_count = sum(1 for c in ranked if c["name"] == "r/roofing")
        assert roofing_count == 1

    def test_boosts_reddit_confirmed_by_api(self):
        claude = [{"name": "r/roofing", "platform": "reddit", "impact": 7, "confidence": 5, "ease": 6}]
        reddit = [{"name": "r/roofing", "platform": "reddit", "subscribers": 10000}]
        ranked = _score_and_rank(claude, reddit)
        assert ranked[0]["confidence"] > 5  # boosted


class TestDiscoverChannels:
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        mock_claude_response = json.dumps([
            {"platform": "reddit", "name": "r/construction", "estimated_audience": "50K",
             "impact": 7, "confidence": 8, "ease": 6, "reasoning": "Active community"},
            {"platform": "facebook", "name": "Quebec Contractors", "estimated_audience": "3K",
             "impact": 8, "confidence": 6, "ease": 5, "reasoning": "Local group"},
        ])

        with (
            patch("src.agents.distribution.channel_discovery.call_claude", new_callable=AsyncMock) as mock_claude,
            patch("src.agents.distribution.channel_discovery._search_reddit", new_callable=AsyncMock) as mock_reddit,
            patch("src.agents.distribution.channel_discovery._validate_via_serper", new_callable=AsyncMock) as mock_serper,
        ):
            mock_claude.return_value = (mock_claude_response, 0.01)
            mock_reddit.return_value = [
                {"platform": "reddit", "name": "r/construction", "subscribers": 50000, "active": True},
            ]
            mock_serper.side_effect = lambda channels, niche: channels  # pass through

            result = await discover_channels(
                "small roofing contractors in Quebec",
                niche="roofing",
            )

        assert len(result) >= 2
        assert all("ice" in ch for ch in result)
        assert result[0]["ice"] >= result[-1]["ice"]  # sorted descending

    @pytest.mark.asyncio
    async def test_handles_empty_claude_response(self):
        with (
            patch("src.agents.distribution.channel_discovery.call_claude", new_callable=AsyncMock) as mock_claude,
            patch("src.agents.distribution.channel_discovery._search_reddit", new_callable=AsyncMock) as mock_reddit,
        ):
            mock_claude.return_value = ("[]", 0.01)
            mock_reddit.return_value = []

            result = await discover_channels("test icp")

        assert isinstance(result, list)


class TestNoSparkToro:
    """Verify SparkToro is completely removed."""

    def test_no_sparktoro_in_deep_scout(self):
        import inspect
        from src.agents.deep_scout import DeepScout
        source = inspect.getsource(DeepScout)
        assert "sparktoro" not in source.lower()
        assert "SparkToro" not in source

    def test_no_sparktoro_in_secrets_schema(self):
        from src.dashboard.routes.secrets_api import SECRETS_SCHEMA
        all_keys = []
        for step in SECRETS_SCHEMA:
            for field in step["fields"]:
                all_keys.append(field["key"])
        assert "SPARKTORO_API_KEY" not in all_keys

    def test_channel_discovery_uses_claude_not_sparktoro(self):
        import inspect
        from src.agents.distribution.channel_discovery import discover_channels
        source = inspect.getsource(discover_channels)
        assert "claude" in source.lower() or "call_claude" in source
        assert "sparktoro" not in source.lower()
