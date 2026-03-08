"""Agent 3: Deep Scout.

Triggered on-demand when an idea scores >= 7.  Performs a comprehensive market
deep dive across 7 steps, producing TWO key outputs:

1. Scout Report (markdown) — saved to ideas.scout_report
2. GTM Playbook (JSON) — saved to gtm_playbooks table, consumed by ALL
   downstream distribution agents (see §13 in SPEC.md)

Step 3 (discover_channels) uses Claude reasoning + Serper validation +
Reddit search for channel discovery, scored with ICE.
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

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "deep_scout.txt"

GTM_SEPARATOR = "---GTM_PLAYBOOK_JSON---"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")



def _score_channels_ice(channels_raw: list[dict]) -> list[dict]:
    """Compute ICE score (Impact × Confidence × Ease) for each channel.

    Each channel dict must have 'impact', 'confidence', 'ease' keys (1-10).
    Returns the list sorted by ICE descending.
    """
    for ch in channels_raw:
        impact = max(1, min(10, int(ch.get("impact", 5))))
        confidence = max(1, min(10, int(ch.get("confidence", 5))))
        ease = max(1, min(10, int(ch.get("ease", 5))))
        ch["impact"] = impact
        ch["confidence"] = confidence
        ch["ease"] = ease
        ch["ice"] = impact * confidence * ease

    return sorted(channels_raw, key=lambda c: c["ice"], reverse=True)


# ── Research helpers ─────────────────────────────────────────────────────────


async def _scrape_url(client: httpx.AsyncClient, url: str, *, max_chars: int = 8_000) -> str:
    """Best-effort scrape of a URL, returning text content."""
    try:
        resp = await client.get(
            url,
            headers={"User-Agent": "FactoryBot/1.0 (research)"},
            follow_redirects=True,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.text[:max_chars]
    except Exception as exc:
        return f"[scrape failed: {exc}]"


async def _search_google_ca(client: httpx.AsyncClient, query: str, num: int = 5) -> str:
    """Quick Google.ca search for competitor / association discovery."""
    try:
        resp = await client.get(
            "https://www.google.ca/search",
            params={"q": query, "num": num, "gl": "ca", "hl": "en"},
            headers={"User-Agent": "FactoryBot/1.0"},
            follow_redirects=True,
            timeout=10,
        )
        return resp.text[:6_000]
    except Exception as exc:
        return f"[search failed: {exc}]"


# ── Report / Playbook parsing ───────────────────────────────────────────────


def _parse_scout_output(response_text: str) -> tuple[str, dict | None]:
    """Split Claude's response into (scout_report_md, gtm_playbook_json).

    The prompt instructs Claude to separate them with GTM_SEPARATOR.
    """
    if GTM_SEPARATOR in response_text:
        parts = response_text.split(GTM_SEPARATOR, 1)
        report_md = parts[0].strip()
        json_text = parts[1].strip()
    else:
        # Try to find a JSON object at the end of the response
        last_brace = response_text.rfind("}")
        first_brace = response_text.rfind("{", 0, last_brace) if last_brace > 0 else -1
        if first_brace > 0:
            # Walk back to find the outermost opening brace
            depth = 0
            for i in range(last_brace, -1, -1):
                if response_text[i] == "}":
                    depth += 1
                elif response_text[i] == "{":
                    depth -= 1
                    if depth == 0:
                        first_brace = i
                        break
            report_md = response_text[:first_brace].strip()
            json_text = response_text[first_brace : last_brace + 1]
        else:
            return response_text.strip(), None

    # Strip markdown code fences from JSON block
    json_clean = json_text.strip()
    if json_clean.startswith("```"):
        lines = json_clean.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        json_clean = "\n".join(lines)

    try:
        playbook = json.loads(json_clean)
        return report_md, playbook
    except json.JSONDecodeError:
        logger.error("deep_scout_gtm_json_failed", raw=json_clean[:500])
        return report_md, None


def _validate_playbook(playbook: dict) -> list[str]:
    """Return a list of missing required keys in the playbook."""
    required = [
        "go_nogo", "confidence", "icp", "channels_ranked",
        "lead_sources", "messaging", "signals",
    ]
    return [k for k in required if k not in playbook]


# ── Agent ────────────────────────────────────────────────────────────────────


class DeepScout(BaseAgent):
    """Deep market research — produces Scout Report + GTM Playbook."""

    agent_name = "deep_scout"
    default_model = "opus"

    async def research_market(self, context) -> dict:
        """Step 1: Scrape Stats Canada, provincial registries, Google.ca for competitors."""
        idea = context.workflow_input()
        idea_name = idea.get("name", "Unknown")
        niche = idea.get("niche", "")
        idea_id = idea.get("idea_id")

        async with httpx.AsyncClient(timeout=15) as client:
            competitor_search = await _search_google_ca(
                client, f"{niche} SaaS Canada software"
            )
            association_search = await _search_google_ca(
                client, f"{niche} association Quebec Canada"
            )
            market_search = await _search_google_ca(
                client, f"{niche} market size Canada Statistics Canada NAICS"
            )

        return {
            "idea_id": idea_id,
            "idea_name": idea_name,
            "niche": niche,
            "idea_data": idea,
            "competitor_search": competitor_search,
            "association_search": association_search,
            "market_search": market_search,
        }

    async def analyze_us_competitor(self, context) -> dict:
        """Step 2: Scrape the US equivalent's website for branding analysis."""
        market = context.step_output("research_market")
        idea_data = market.get("idea_data", {})
        us_url = idea_data.get("us_equivalent_url", "")

        pages = {}
        if us_url:
            base = us_url.rstrip("/")
            async with httpx.AsyncClient(timeout=15) as client:
                for page in ["", "/pricing", "/features", "/about"]:
                    url = f"{base}{page}"
                    pages[page or "/"] = await _scrape_url(client, url)

        return {
            "us_equivalent": idea_data.get("us_equivalent", ""),
            "us_url": us_url,
            "pages_scraped": list(pages.keys()),
            "page_content": pages,
        }

    async def discover_channels(self, context) -> dict:
        """Step 3: Claude reasoning + Serper validation + Reddit search for channel discovery."""
        from src.agents.distribution.channel_discovery import discover_channels as _discover

        market = context.step_output("research_market")
        niche = market.get("niche", "")

        icp_description = (
            f"small {niche} business owners and contractors in Quebec, Canada"
        )

        ranked_channels = await _discover(icp_description, niche=niche)

        return {
            "ranked_channels": ranked_channels,
            "icp_description": icp_description,
            "channels_found": len(ranked_channels),
        }

    async def research_regulations(self, context) -> dict:
        """Step 4: Provincial regulations, bilingual requirements, certifications."""
        market = context.step_output("research_market")
        niche = market.get("niche", "")

        async with httpx.AsyncClient(timeout=15) as client:
            regulations = await _search_google_ca(
                client, f"{niche} regulations Quebec licence RBQ provincial requirements"
            )
            bilingual = await _search_google_ca(
                client, f"Loi 101 bilingual requirements software Quebec OQLF"
            )
            casl = await _search_google_ca(
                client, f"CASL anti-spam law Canada B2B email requirements 2026"
            )

        return {
            "regulations_search": regulations,
            "bilingual_search": bilingual,
            "casl_search": casl,
        }

    async def generate_gtm_playbook(self, context) -> dict:
        """Step 5: Synthesize all research into Scout Report + GTM Playbook via Claude Opus.

        KNOWLEDGE-INFORMED: queries factory_knowledge for relevant insights
        before generating, so Business #5 benefits from Businesses #1-4.
        """
        from src.knowledge import query_knowledge, format_knowledge_for_prompt

        market = context.step_output("research_market")
        us_competitor = context.step_output("analyze_us_competitor")
        channels = context.step_output("discover_channels")
        regulations = context.step_output("research_regulations")

        niche = market.get("niche", "")

        # Query accumulated knowledge for this vertical
        prior_knowledge = await query_knowledge(vertical=niche, limit=20)
        knowledge_block = format_knowledge_for_prompt(prior_knowledge)

        model_tier = await self.check_budget()
        system_prompt = _load_prompt()
        if knowledge_block:
            system_prompt += f"\n\n{knowledge_block}"

        research_payload = {
            "idea": market.get("idea_data", {}),
            "market_research": {
                "competitor_search": market.get("competitor_search", ""),
                "association_search": market.get("association_search", ""),
                "market_search": market.get("market_search", ""),
            },
            "us_competitor": {
                "name": us_competitor.get("us_equivalent", ""),
                "url": us_competitor.get("us_url", ""),
                "pages": us_competitor.get("page_content", {}),
            },
            "channel_research": {
                "ranked_channels": channels.get("ranked_channels", []),
                "channels_found": channels.get("channels_found", 0),
            },
            "regulations": regulations,
            "prior_knowledge_count": len(prior_knowledge),
        }

        user_payload = json.dumps(research_payload, default=str)[:60_000]

        response_text, cost = await call_claude(
            model_tier=model_tier,
            system=system_prompt,
            user=user_payload,
            max_tokens=8192,
            temperature=0.3,
        )

        await self.log_execution(
            action="generate_gtm_playbook",
            result={"response_length": len(response_text)},
            cost_usd=cost,
        )

        scout_report, playbook = _parse_scout_output(response_text)

        # Validate and enrich playbook
        if playbook:
            missing = _validate_playbook(playbook)
            if missing:
                logger.warning("playbook_missing_keys", missing=missing)

            # Re-score channels with ICE if present
            ranked = playbook.get("channels_ranked", [])
            if ranked:
                playbook["channels_ranked"] = _score_channels_ice(ranked)

        return {
            "scout_report": scout_report,
            "gtm_playbook": playbook,
            "cost_usd": cost,
        }

    async def save_and_recommend(self, context) -> dict:
        """Step 6: Persist Scout Report + GTM Playbook, update idea status."""
        market = context.step_output("research_market")
        gtm_result = context.step_output("generate_gtm_playbook")

        idea_id = market.get("idea_id")
        scout_report = gtm_result.get("scout_report", "")
        playbook = gtm_result.get("gtm_playbook")

        go_nogo = playbook.get("go_nogo", "nogo") if playbook else "nogo"
        confidence = playbook.get("confidence", 0) if playbook else 0
        new_status = "validated" if go_nogo == "go" else "killed"

        async with SessionLocal() as db:
            # Save scout report to ideas table
            if idea_id:
                await db.execute(
                    text(
                        "UPDATE ideas SET scout_report = :report, "
                        "status = :status, updated_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {"report": scout_report, "status": new_status, "id": idea_id},
                )

            # Save GTM Playbook (even on nogo for reference)
            business_id = None
            if playbook and idea_id:
                # Check if a business already exists for this idea
                biz_row = (
                    await db.execute(
                        text("SELECT id FROM businesses WHERE idea_id = :idea_id"),
                        {"idea_id": idea_id},
                    )
                ).fetchone()

                if biz_row:
                    business_id = biz_row.id
                elif go_nogo == "go":
                    biz_result = await db.execute(
                        text(
                            "INSERT INTO businesses (idea_id, name, niche, status) "
                            "VALUES (:idea_id, :name, :niche, 'setup') RETURNING id"
                        ),
                        {
                            "idea_id": idea_id,
                            "name": market.get("idea_name", "Unnamed"),
                            "niche": market.get("niche"),
                        },
                    )
                    business_id = biz_result.fetchone().id

                if business_id:
                    await db.execute(
                        text(
                            "INSERT INTO gtm_playbooks (business_id, config, last_updated_by) "
                            "VALUES (:biz, :config, 'deep_scout') "
                            "ON CONFLICT (business_id) DO UPDATE SET "
                            "config = EXCLUDED.config, version = gtm_playbooks.version + 1, "
                            "last_updated_by = 'deep_scout', updated_at = NOW()"
                        ),
                        {"biz": business_id, "config": json.dumps(playbook)},
                    )

            await db.commit()

        await self.log_execution(
            action="save_and_recommend",
            result={
                "idea_id": idea_id,
                "business_id": business_id,
                "go_nogo": go_nogo,
                "confidence": confidence,
                "playbook_saved": playbook is not None,
            },
        )

        return {
            "idea_id": idea_id,
            "business_id": business_id,
            "go_nogo": go_nogo,
            "confidence": confidence,
            "scout_report_length": len(scout_report),
            "playbook_saved": playbook is not None,
        }


def register(hatchet_instance) -> type:
    """Register DeepScout as a Hatchet workflow (on-demand, not cron)."""

    @hatchet_instance.workflow(name="deep-scout")
    class _RegisteredDeepScout(DeepScout):
        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def research_market(self, context) -> dict:
            return await DeepScout.research_market(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def analyze_us_competitor(self, context) -> dict:
            return await DeepScout.analyze_us_competitor(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def discover_channels(self, context) -> dict:
            return await DeepScout.discover_channels(self, context)

        @hatchet_instance.task(execution_timeout="3m", retries=2)
        async def research_regulations(self, context) -> dict:
            return await DeepScout.research_regulations(self, context)

        @hatchet_instance.task(execution_timeout="10m", retries=2)
        async def generate_gtm_playbook(self, context) -> dict:
            return await DeepScout.generate_gtm_playbook(self, context)

        @hatchet_instance.task(execution_timeout="5m", retries=2)
        async def save_and_recommend(self, context) -> dict:
            return await DeepScout.save_and_recommend(self, context)

    return _RegisteredDeepScout
