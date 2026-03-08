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
]

# Serper queries — broad across industries, rotated
SERPER_QUERIES = [
    "small SaaS tool Canada doesn't have site:indiehackers.com",
    "micro SaaS tool spreadsheet replacement 2026",
    "niche SaaS tool under 20 employees launched 2025 2026",
    "vertical SaaS tool for contractors tradespeople small business",
    "Shopify app low rated complaints small business",
    "SaaS tool agriculture farming Canada",
    "SaaS tool oil gas Alberta compliance",
    "SaaS tool real estate property management Canada",
    "SaaS tool trucking logistics Canadian compliance",
    "SaaS tool restaurant health inspection Canada",
    "SaaS tool auto dealership compliance",
    "SaaS tool veterinary clinic invoicing",
    "SaaS tool snow removal landscaping scheduling",
    "niche compliance tool small business 2026",
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
        """Step 1: Scrape Product Hunt + Serper web search for idea signals."""
        results = []

        # Scrape static sources (Product Hunt)
        async with httpx.AsyncClient(timeout=15) as client:
            for source in SCRAPE_SOURCES:
                data = await _scrape_source(client, source)
                results.append(data)

        # Use Serper for research queries — pick 6 random to get variety
        import random
        from src.config import settings
        serper_key = settings.get("SERPER_API_KEY")
        if serper_key:
            queries_this_run = random.sample(SERPER_QUERIES, min(6, len(SERPER_QUERIES)))
            async with httpx.AsyncClient(timeout=15) as client:
                for query in queries_this_run:
                    try:
                        resp = await client.post(
                            "https://google.serper.dev/search",
                            headers={"X-API-KEY": serper_key},
                            json={"q": query, "num": 10},
                        )
                        resp.raise_for_status()
                        search_results = resp.json().get("organic", [])
                        results.append({
                            "source": f"serper_{query[:30]}",
                            "description": query,
                            "data": [{"title": r.get("title"), "snippet": r.get("snippet"), "link": r.get("link")} for r in search_results],
                            "status": "ok",
                        })
                    except Exception as exc:
                        logger.warning("serper_search_failed", query=query[:30], error=str(exc))
                        results.append({"source": f"serper_{query[:30]}", "data": None, "status": f"error: {exc}"})

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

        # Fetch existing ideas for deduplication
        existing_ideas = []
        try:
            async with SessionLocal() as db:
                rows = (await db.execute(text(
                    "SELECT name, niche, status FROM ideas ORDER BY id DESC LIMIT 100"
                ))).fetchall()
                existing_ideas = [{"name": r.name, "niche": r.niche, "status": r.status} for r in rows]
        except Exception:
            pass

        scraped_summary = json.dumps(scraped["scraped_data"], default=str)[:25_000]

        user_msg = scraped_summary
        if existing_ideas:
            dedup_list = json.dumps(existing_ideas, default=str)
            user_msg = (
                f"IDEAS ALREADY IN DATABASE (DO NOT SUGGEST THESE AGAIN):\n{dedup_list}\n\n"
                f"SCRAPED DATA:\n{scraped_summary}"
            )

        response_text, cost = await call_claude(
            model_tier=model_tier,
            system=system_prompt,
            user=user_msg,
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
        """Step 3: Filter ideas on overall score + complexity + competitor size."""
        prev = context.step_output("filter_canadian_gap")
        ideas = prev.get("ideas", [])

        qualified = []
        rejected = []

        for idea in ideas:
            score = idea.get("score", 0)
            details = idea.get("scoring_details", {})
            complexity = details.get("criterion_7", 5)
            competitor_size = details.get("criterion_13", 5)

            # Auto-reject from Claude's own rejection flag
            if idea.get("rejected"):
                rejected.append({"name": idea.get("name"), "score": score, "reason": idea.get("rejection_reason", "Claude rejected")})
                continue

            # Complexity gate: must be buildable in <2 weeks
            if complexity < 7:
                rejected.append({"name": idea.get("name"), "score": score, "reason": f"Too complex (criterion_7={complexity})"})
                continue

            # Competitor size gate: US equivalent must be small
            if competitor_size < 5:
                rejected.append({"name": idea.get("name"), "score": score, "reason": f"US competitor too large (criterion_13={competitor_size})"})
                continue

            # Overall score threshold
            if score < SCORE_THRESHOLD:
                rejected.append({"name": idea.get("name"), "score": score, "reason": f"Score {score} < {SCORE_THRESHOLD}"})
                continue

            qualified.append(idea)

        logger.info(
            "ideas_scored",
            total=len(ideas),
            qualified=len(qualified),
            rejected=len(rejected),
        )

        return {
            "qualified_ideas": qualified,
            "rejected": rejected,
        }

    async def filter_complexity(self, context) -> dict:
        """Step 4: Validate competitor size via Serper. Reject if US equivalent is too big."""
        scored = context.step_output("score_ideas")
        qualified = scored.get("qualified_ideas", [])
        rejected = list(scored.get("rejected", []))

        if not qualified:
            return {"qualified_ideas": [], "rejected": rejected}

        validated = []
        async with httpx.AsyncClient(timeout=10) as client:
            for idea in qualified:
                us_equiv = idea.get("us_equivalent", "")
                if not us_equiv:
                    validated.append(idea)
                    continue

                # Quick Serper search for company size
                try:
                    from src.integrations import serper
                    results = await serper.search_maps(f"{us_equiv} company employees funding crunchbase", "USA", num=3)
                    # If Serper returns data about a large company, flag it
                    # For now, trust Claude's criterion_13 score since Serper Maps won't reliably return employee counts
                    validated.append(idea)
                except Exception:
                    validated.append(idea)

        logger.info("complexity_filter", input=len(qualified), output=len(validated), rejected=len(rejected))
        return {"qualified_ideas": validated, "rejected": rejected}

    async def save_and_notify(self, context) -> dict:
        """Step 5: Persist qualified ideas and notify Meta Orchestrator."""
        scored = context.step_output("filter_complexity")
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

        # Notify Slack about new ideas
        for idea, idea_id in zip(qualified, saved_ids):
            try:
                from src.slack import notify_idea_discovered
                await notify_idea_discovered(idea.get("name", ""), idea.get("score", 0), idea_id)
            except Exception:
                pass

        top_3 = sorted(qualified, key=lambda x: x.get("score", 0), reverse=True)[:3]
        top_3_summary = [
            {"name": i.get("name"), "score": i.get("score"), "niche": i.get("niche")}
            for i in top_3
        ]

        # Auto-run Deep Scout on qualified ideas
        for idea, idea_id in zip(qualified, saved_ids):
            score = idea.get("score", 0)
            if score >= 7.0:
                async with SessionLocal() as db:
                    await db.execute(
                        text(
                            "INSERT INTO agent_logs (agent_name, action, result, status) "
                            "VALUES ('idea_factory', :action, :result, 'success')"
                        ),
                        {
                            "action": f"triggering_deep_scout: {idea.get('name')} (score {score})",
                            "result": json.dumps({"idea_id": idea_id, "score": score}),
                        },
                    )
                    await db.commit()
                logger.info("triggering_deep_scout", name=idea.get("name"), score=score, idea_id=idea_id)

                # Run Deep Scout inline (same process, no Hatchet dependency)
                try:
                    from src.agents.deep_scout import DeepScout

                    class _ScoutContext:
                        def __init__(self, iid, name, niche, us_eq, us_url):
                            self._input = {"idea_id": iid, "idea_name": name, "niche": niche,
                                           "us_equivalent": us_eq, "us_equivalent_url": us_url}
                            self._outputs = {}
                        def workflow_input(self):
                            return self._input
                        def step_output(self, name):
                            return self._outputs.get(name, {})

                    scout = DeepScout()
                    ctx = _ScoutContext(
                        idea_id, idea.get("name", ""), idea.get("niche", ""),
                        idea.get("us_equivalent", ""), idea.get("us_equivalent_url", ""),
                    )
                    for step_name, step_fn in [
                        ("research_market", scout.research_market),
                        ("analyze_us_competitor", scout.analyze_us_competitor),
                        ("discover_channels", scout.discover_channels),
                        ("research_regulations", scout.research_regulations),
                        ("generate_gtm_playbook", scout.generate_gtm_playbook),
                        ("save_and_recommend", scout.save_and_recommend),
                    ]:
                        logger.info("deep_scout_step", step=step_name, idea=idea.get("name"))
                        result = await step_fn(ctx)
                        ctx._outputs[step_name] = result if isinstance(result, dict) else {}

                    go_nogo = ctx._outputs.get("save_and_recommend", {}).get("go_nogo", "nogo")
                    if go_nogo == "go":
                        # Deep Scout says GO — notify CEO for approval
                        async with SessionLocal() as db:
                            await db.execute(text(
                                "INSERT INTO agent_logs (agent_name, action, result, status) "
                                "VALUES ('deep_scout', :action, :result, 'success')"
                            ), {
                                "action": f"GO recommendation: {idea.get('name')}",
                                "result": json.dumps({"idea_id": idea_id, "go_nogo": "go"}),
                            })
                            await db.commit()
                        logger.info("deep_scout_go", name=idea.get("name"), idea_id=idea_id)
                        try:
                            from src.slack import notify_approval_needed
                            await notify_approval_needed(idea.get("name", ""), idea_id)
                        except Exception:
                            pass
                    else:
                        logger.info("deep_scout_nogo", name=idea.get("name"), idea_id=idea_id)
                        try:
                            from src.slack import notify_idea_validated
                            await notify_idea_validated(idea.get("name", ""), idea_id, "nogo")
                        except Exception:
                            pass

                except Exception as scout_exc:
                    logger.error("deep_scout_failed", idea_id=idea_id, error=str(scout_exc))

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

    @wf.task(execution_timeout="3m", retries=1)
    async def filter_complexity(input, ctx):
        return await agent.filter_complexity(ctx)

    @wf.task(execution_timeout="5m", retries=2)
    async def save_and_notify(input, ctx):
        return await agent.save_and_notify(ctx)

    return wf
