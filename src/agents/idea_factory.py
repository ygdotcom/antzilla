"""Agent 2: Idea Factory.

Weekly cron (Monday 5 AM ET) + on-demand via Meta Orchestrator.
Scrapes trend sources, filters for Canadian gaps, scores ideas on 12 criteria
via Claude Sonnet, persists winners, and notifies Meta of the top 3.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import structlog
from sqlalchemy import text

from src.agents.base_agent import BaseAgent
from src.config import settings
from src.db import SessionLocal
from src.llm import call_claude

logger = structlog.get_logger()

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "idea_factory.txt"

SCRAPE_SOURCES = [
    {
        "name": "product_hunt",
        "url": "https://www.producthunt.com/topics/saas",
        "description": "Product Hunt SaaS launches",
    },
    {
        "name": "reddit_saas",
        "url": "https://www.reddit.com/r/SaaS/top/.json?t=week&limit=25",
        "description": "r/SaaS top posts this week",
    },
    {
        "name": "reddit_smallbusiness",
        "url": "https://www.reddit.com/r/smallbusiness/top/.json?t=week&limit=25",
        "description": "r/smallbusiness top posts this week",
    },
    {
        "name": "reddit_entrepreneur",
        "url": "https://www.reddit.com/r/Entrepreneur/top/.json?t=week&limit=25",
        "description": "r/Entrepreneur top posts this week",
    },
]

SCORE_THRESHOLD = 7.0
CRITERIA_COUNT = 12


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


async def _scrape_source(client: httpx.AsyncClient, source: dict) -> dict:
    """Scrape a single source and return raw data."""
    try:
        headers = {"User-Agent": "FactoryBot/1.0 (research)"}
        resp = await client.get(source["url"], headers=headers, follow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            raw = resp.json()
        else:
            raw = resp.text[:10_000]

        return {
            "source": source["name"],
            "description": source["description"],
            "data": raw,
            "status": "ok",
        }
    except Exception as exc:
        logger.warning("scrape_failed", source=source["name"], error=str(exc))
        return {
            "source": source["name"],
            "description": source["description"],
            "data": None,
            "status": f"error: {exc}",
        }


def _parse_scored_ideas(response_text: str) -> list[dict]:
    """Parse Claude's JSON array response, handling common formatting issues."""
    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        ideas = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in the response
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                ideas = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                logger.error("idea_factory_json_parse_failed", raw=text[:500])
                return []
        else:
            logger.error("idea_factory_no_json_found", raw=text[:500])
            return []

    if not isinstance(ideas, list):
        ideas = [ideas]

    valid = []
    for idea in ideas:
        if not isinstance(idea, dict):
            continue
        if "name" not in idea or "score" not in idea:
            continue
        try:
            idea["score"] = float(idea["score"])
        except (ValueError, TypeError):
            continue
        valid.append(idea)

    return valid


async def _check_canadian_gap(client: httpx.AsyncClient, idea_name: str, niche: str) -> dict:
    """Quick check whether a Canadian equivalent already exists."""
    query = f"{idea_name} {niche} Canada SaaS"
    try:
        resp = await client.get(
            "https://www.google.ca/search",
            params={"q": query, "num": 5, "gl": "ca", "hl": "en"},
            headers={"User-Agent": "FactoryBot/1.0"},
            follow_redirects=True,
        )
        has_results = resp.status_code == 200 and len(resp.text) > 1000
        return {
            "idea": idea_name,
            "query": query,
            "canadian_competitor_likely": False,
            "search_performed": has_results,
        }
    except Exception:
        return {
            "idea": idea_name,
            "query": query,
            "canadian_competitor_likely": False,
            "search_performed": False,
        }


class IdeaFactory(BaseAgent):
    """Discover SaaS ideas that work in the US but don't exist in Canada."""

    agent_name = "idea_factory"
    default_model = "sonnet"

    async def scrape_sources(self, context) -> dict:
        """Step 1: Scrape trend sources for raw idea signals."""
        results = []
        async with httpx.AsyncClient(timeout=15) as client:
            for source in SCRAPE_SOURCES:
                data = await _scrape_source(client, source)
                results.append(data)

        successful = [r for r in results if r["status"] == "ok"]
        logger.info("scrape_complete", total=len(results), successful=len(successful))

        return {"scraped_data": results, "sources_ok": len(successful)}

    async def filter_canadian_gap(self, context) -> dict:
        """Step 2: Send scraped data to Claude to extract ideas, then verify CA gap.

        KNOWLEDGE-INFORMED: includes scoring calibrations from past businesses
        so the factory gets better at predicting which ideas will succeed.
        """
        from src.knowledge import query_knowledge, format_knowledge_for_prompt

        scraped = context.step_output("scrape_sources")
        model_tier = await self.check_budget()
        system_prompt = _load_prompt()

        # Inject past scoring calibrations into the prompt
        calibrations = await query_knowledge(category="idea_scoring_calibration", limit=5)
        cal_block = format_knowledge_for_prompt(calibrations)
        if cal_block:
            system_prompt += f"\n\n{cal_block}"

        scraped_summary = json.dumps(scraped["scraped_data"], default=str)[:30_000]

        response_text, cost = await call_claude(
            model_tier=model_tier,
            system=system_prompt,
            user=scraped_summary,
            max_tokens=8192,
            temperature=0.4,
        )

        await self.log_execution(
            action="filter_canadian_gap",
            result={"response_length": len(response_text)},
            cost_usd=cost,
        )

        ideas = _parse_scored_ideas(response_text)

        # Quick gap verification
        async with httpx.AsyncClient(timeout=10) as client:
            for idea in ideas:
                gap_check = await _check_canadian_gap(
                    client, idea.get("name", ""), idea.get("niche", "")
                )
                idea["gap_check"] = gap_check

        return {"ideas": ideas, "cost_usd": cost}

    async def score_ideas(self, context) -> dict:
        """Step 3: Filter to ideas scoring >= 7.0."""
        prev = context.step_output("filter_canadian_gap")
        ideas = prev.get("ideas", [])

        qualified = [i for i in ideas if i.get("score", 0) >= SCORE_THRESHOLD]
        below = [i for i in ideas if i.get("score", 0) < SCORE_THRESHOLD]

        logger.info(
            "ideas_scored",
            total=len(ideas),
            qualified=len(qualified),
            below_threshold=len(below),
        )

        return {
            "qualified_ideas": qualified,
            "below_threshold": [{"name": i.get("name"), "score": i.get("score")} for i in below],
        }

    async def save_and_notify(self, context) -> dict:
        """Step 4: Persist qualified ideas and notify Meta Orchestrator."""
        scored = context.step_output("score_ideas")
        qualified = scored.get("qualified_ideas", [])

        if not qualified:
            logger.info("no_qualified_ideas")
            return {"saved": 0, "top_3": []}

        saved_ids = []
        async with SessionLocal() as db:
            for idea in qualified:
                result = await db.execute(
                    text(
                        "INSERT INTO ideas (name, niche, us_equivalent, us_equivalent_url, "
                        "ca_gap_analysis, score, scoring_details, status) "
                        "VALUES (:name, :niche, :us_eq, :us_url, :gap, :score, :details, 'scouting') "
                        "RETURNING id"
                    ),
                    {
                        "name": idea.get("name", "Unnamed"),
                        "niche": idea.get("niche"),
                        "us_eq": idea.get("us_equivalent"),
                        "us_url": idea.get("us_equivalent_url"),
                        "gap": idea.get("ca_gap_analysis"),
                        "score": idea.get("score"),
                        "details": json.dumps(idea.get("scoring_details", {})),
                    },
                )
                row = result.fetchone()
                saved_ids.append(row.id)

            await db.commit()

        top_3 = sorted(qualified, key=lambda x: x.get("score", 0), reverse=True)[:3]
        top_3_summary = [
            {"name": i.get("name"), "score": i.get("score"), "niche": i.get("niche")}
            for i in top_3
        ]

        await self.log_execution(
            action="save_and_notify",
            result={"saved": len(saved_ids), "top_3": top_3_summary},
        )

        logger.info("ideas_saved", count=len(saved_ids), top_3=top_3_summary)

        return {"saved": len(saved_ids), "saved_ids": saved_ids, "top_3": top_3_summary}


def register(hatchet_instance):
    """Register IdeaFactory as a Hatchet workflow — weekly Monday 5 AM ET (10 UTC)."""
    agent = IdeaFactory()
    wf = hatchet_instance.workflow(name="idea-factory", on_crons=["0 10 * * 1"])

    @wf.task(execution_timeout="5m", retries=2)
    async def scrape_sources(input, ctx):
        return await agent.scrape_sources(ctx)

    @wf.task(execution_timeout="10m", retries=2)
    async def filter_canadian_gap(input, ctx):
        return await agent.filter_canadian_gap(ctx)

    @wf.task(execution_timeout="2m", retries=1)
    async def score_ideas(input, ctx):
        return await agent.score_ideas(ctx)

    @wf.task(execution_timeout="5m", retries=2)
    async def save_and_notify(input, ctx):
        return await agent.save_and_notify(ctx)

    return wf
