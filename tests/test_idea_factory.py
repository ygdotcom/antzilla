"""Tests for the Idea Factory agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.idea_factory import (
    SCORE_THRESHOLD,
    IdeaFactory,
    _load_prompt,
    _parse_scored_ideas,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    return IdeaFactory()


@pytest.fixture
def sample_ideas_json():
    return json.dumps([
        {
            "name": "Quote OS",
            "niche": "construction quoting",
            "us_equivalent": "Jobber",
            "us_equivalent_url": "https://getjobber.com",
            "ca_gap_analysis": "No Canadian-specific quoting tool",
            "score": 8.5,
            "scoring_details": {f"criterion_{i}": 7 + (i % 3) for i in range(1, 13)},
            "tam_estimate": "~15000 contractors in Quebec",
            "pricing_hypothesis": "$49/mo based on Jobber pricing",
            "mvp_complexity": "medium",
        },
        {
            "name": "AR Collections",
            "niche": "accounts receivable",
            "us_equivalent": "Tesorio",
            "us_equivalent_url": "https://www.tesorio.com",
            "ca_gap_analysis": "No AR tool for Quebec payment culture",
            "score": 7.2,
            "scoring_details": {f"criterion_{i}": 6 + (i % 4) for i in range(1, 13)},
            "tam_estimate": "~8000 SMBs in Quebec",
            "pricing_hypothesis": "$79/mo",
            "mvp_complexity": "medium",
        },
        {
            "name": "Bad Idea",
            "niche": "blockchain pet food",
            "us_equivalent": "None",
            "us_equivalent_url": "",
            "ca_gap_analysis": "Nobody wants this",
            "score": 3.1,
            "scoring_details": {f"criterion_{i}": 3 for i in range(1, 13)},
            "tam_estimate": "~12 people",
            "pricing_hypothesis": "$10/mo maybe",
            "mvp_complexity": "high",
        },
    ])


# ── Prompt Tests ──────────────────────────────────────────────────────────────


class TestPrompt:
    def test_load_prompt(self):
        prompt = _load_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_prompt_has_12_criteria(self):
        prompt = _load_prompt()
        for i in range(1, 13):
            assert f"{i}." in prompt, f"Criterion {i} not found in prompt"

    def test_prompt_requests_json(self):
        prompt = _load_prompt()
        assert "JSON" in prompt


# ── Parser Tests ──────────────────────────────────────────────────────────────


class TestParseScoreIdeas:
    def test_valid_json_array(self, sample_ideas_json):
        ideas = _parse_scored_ideas(sample_ideas_json)
        assert len(ideas) == 3
        assert ideas[0]["name"] == "Quote OS"
        assert ideas[0]["score"] == 8.5

    def test_json_with_code_fences(self, sample_ideas_json):
        wrapped = f"```json\n{sample_ideas_json}\n```"
        ideas = _parse_scored_ideas(wrapped)
        assert len(ideas) == 3

    def test_json_with_preamble(self, sample_ideas_json):
        text = f"Here are the ideas:\n\n{sample_ideas_json}\n\nDone."
        ideas = _parse_scored_ideas(text)
        assert len(ideas) == 3

    def test_empty_response(self):
        ideas = _parse_scored_ideas("")
        assert ideas == []

    def test_invalid_json(self):
        ideas = _parse_scored_ideas("this is not json at all")
        assert ideas == []

    def test_missing_name_filtered(self):
        ideas = _parse_scored_ideas(json.dumps([{"score": 5.0}]))
        assert len(ideas) == 0

    def test_missing_score_filtered(self):
        ideas = _parse_scored_ideas(json.dumps([{"name": "Test"}]))
        assert len(ideas) == 0

    def test_single_object_not_array(self):
        single = json.dumps({
            "name": "Solo Idea",
            "score": 7.5,
            "niche": "test",
        })
        ideas = _parse_scored_ideas(single)
        assert len(ideas) == 1
        assert ideas[0]["name"] == "Solo Idea"


# ── Config Tests ──────────────────────────────────────────────────────────────


class TestIdeaFactoryConfig:
    def test_agent_name(self, agent):
        assert agent.agent_name == "idea_factory"

    def test_default_model(self, agent):
        assert agent.default_model == "sonnet"


# ── Step Tests ────────────────────────────────────────────────────────────────


class TestScrapeStep:
    @pytest.mark.asyncio
    async def test_scrape_returns_data(self, agent):
        with patch("src.agents.idea_factory.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/html"}
            mock_response.text = "<html>data</html>"
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            ctx = MagicMock()
            result = await agent.scrape_sources(ctx)

        assert "scraped_data" in result
        assert result["sources_ok"] > 0


class TestFilterStep:
    @pytest.mark.asyncio
    async def test_filter_parses_ideas(self, agent, sample_ideas_json):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "scraped_data": [{"source": "test", "data": "data", "status": "ok"}],
            "sources_ok": 1,
        })

        with (
            patch.object(agent, "check_budget", new_callable=AsyncMock, return_value="sonnet"),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
            patch("src.agents.idea_factory.call_claude", new_callable=AsyncMock) as mock_claude,
            patch("src.agents.idea_factory._check_canadian_gap", new_callable=AsyncMock) as mock_gap,
            patch("src.knowledge.SessionLocal") as mock_sl,
        ):
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
            mock_sl.return_value = mock_db
            mock_claude.return_value = (sample_ideas_json, 0.02)
            mock_gap.return_value = {
                "idea": "test",
                "canadian_competitor_likely": False,
                "search_performed": True,
            }
            result = await agent.filter_canadian_gap(ctx)

        assert len(result["ideas"]) == 3


class TestScoreStep:
    @pytest.mark.asyncio
    async def test_score_filters_by_threshold(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "ideas": [
                {"name": "Good", "score": 8.5},
                {"name": "Ok", "score": 7.0},
                {"name": "Bad", "score": 3.1},
            ],
            "cost_usd": 0.01,
        })

        result = await agent.score_ideas(ctx)

        assert len(result["qualified_ideas"]) == 2
        assert len(result["below_threshold"]) == 1
        assert result["below_threshold"][0]["name"] == "Bad"

    @pytest.mark.asyncio
    async def test_threshold_is_7(self):
        assert SCORE_THRESHOLD == 7.0


class TestSaveStep:
    @pytest.mark.asyncio
    async def test_no_ideas_saves_nothing(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={"qualified_ideas": []})

        result = await agent.save_and_notify(ctx)
        assert result["saved"] == 0

    @pytest.mark.asyncio
    async def test_saves_qualified_ideas(self, agent):
        ctx = MagicMock()
        ctx.step_output = MagicMock(return_value={
            "qualified_ideas": [
                {"name": "Quote OS", "score": 8.5, "niche": "construction",
                 "us_equivalent": "Jobber", "us_equivalent_url": "https://getjobber.com",
                 "ca_gap_analysis": "No Canadian tool", "scoring_details": {}},
            ],
        })

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_row = MagicMock()
        mock_row.id = 42
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=mock_row)))
        mock_db.commit = AsyncMock()

        with (
            patch("src.agents.idea_factory.SessionLocal", return_value=mock_db),
            patch.object(agent, "log_execution", new_callable=AsyncMock),
        ):
            result = await agent.save_and_notify(ctx)

        assert result["saved"] == 1
        assert 42 in result["saved_ids"]
        assert result["top_3"][0]["name"] == "Quote OS"
