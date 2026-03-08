"""Channel discovery — replaces SparkToro with Claude reasoning + Serper validation + Reddit search.

Takes an ICP description, returns ranked channels with ICE scores.
Used by Deep Scout step 3 (discover_channels) to populate GTM Playbooks.
"""

from __future__ import annotations

import json
import re

import httpx
import structlog

from src.integrations import serper
from src.llm import call_claude

logger = structlog.get_logger()

CHANNEL_REASONING_PROMPT = """\
Given this ICP (Ideal Customer Profile), identify the top 10 online channels where this audience spends time.

For each channel, provide:
- platform: one of "reddit", "facebook", "linkedin", "forum", "association", "marketplace", "youtube", "podcast"
- name: specific name (subreddit name like "r/roofing", Facebook group name, association URL, etc.)
- estimated_audience: rough size ("5K members", "12K subscribers", etc.)
- impact: 1-10 (how likely reaching this audience leads to signups)
- confidence: 1-10 (how confident you are this channel is active and relevant)
- ease: 1-10 (how easy it is to participate without getting banned)
- reasoning: one sentence explaining why this channel matters

Focus on CANADIAN channels when possible. Include:
- Relevant subreddits (check if r/[industry]Canada or r/[industry] exists)
- Facebook Groups (industry-specific, ideally Quebec/Canada focused)
- LinkedIn communities or hashtags
- Industry associations (national and provincial, with URLs if known)
- Relevant marketplaces (QuickBooks App Store, Shopify, etc.)
- Forums and community sites
- YouTube channels or podcasts the ICP follows

Respond ONLY in JSON array format.
"""


def _compute_ice(channel: dict) -> int:
    """Compute ICE score from individual dimensions, clamping to 1-10."""
    impact = max(1, min(10, int(channel.get("impact", 5))))
    confidence = max(1, min(10, int(channel.get("confidence", 5))))
    ease = max(1, min(10, int(channel.get("ease", 5))))
    channel["impact"] = impact
    channel["confidence"] = confidence
    channel["ease"] = ease
    channel["ice"] = impact * confidence * ease
    return channel["ice"]


async def _claude_channel_reasoning(icp_description: str) -> list[dict]:
    """Ask Claude to reason about which channels the ICP uses."""
    response, cost = await call_claude(
        model_tier="haiku",
        system=CHANNEL_REASONING_PROMPT,
        user=icp_description,
        max_tokens=4096,
        temperature=0.4,
    )

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        channels = json.loads(text)
        if not isinstance(channels, list):
            channels = [channels]
        return channels
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning("channel_reasoning_parse_failed")
    return []


async def _validate_via_serper(channels: list[dict], niche: str) -> list[dict]:
    """Validate Claude's suggestions by searching Google for evidence."""
    validation_queries = [
        f"{niche} association Canada",
        f"{niche} association Quebec",
        f"{niche} Facebook group",
        f"site:reddit.com {niche}",
        f"{niche} trade show Canada 2026",
    ]

    found_names: set[str] = set()
    for query in validation_queries:
        results = await serper.search_maps(query, "Canada", num=5)
        for r in results:
            found_names.add(r.get("name", "").lower())

    # Also do a web search for each channel name
    for ch in channels:
        name = ch.get("name", "")
        if not name:
            continue
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://www.google.ca/search",
                    params={"q": name, "num": 3},
                    headers={"User-Agent": "FactoryBot/1.0"},
                    follow_redirects=True,
                )
                ch["_verified"] = resp.status_code == 200 and len(resp.text) > 1000
        except Exception:
            ch["_verified"] = False

    return channels


async def _search_reddit(keywords: list[str]) -> list[dict]:
    """Search Reddit for active subreddits matching keywords. Free, no API key."""
    subreddits = []
    async with httpx.AsyncClient(timeout=10) as client:
        for kw in keywords[:5]:
            try:
                resp = await client.get(
                    "https://www.reddit.com/subreddits/search.json",
                    params={"q": kw, "limit": 5},
                    headers={"User-Agent": "FactoryBot/1.0 (research)"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for sub in data.get("data", {}).get("children", []):
                        sub_data = sub.get("data", {})
                        subscribers = sub_data.get("subscribers", 0)
                        if subscribers > 100:
                            subreddits.append({
                                "platform": "reddit",
                                "name": f"r/{sub_data.get('display_name', '')}",
                                "estimated_audience": f"{subscribers:,} subscribers",
                                "subscribers": subscribers,
                                "active": sub_data.get("accounts_active", 0) > 0,
                                "description": sub_data.get("public_description", "")[:200],
                            })
            except Exception:
                continue

    # Deduplicate by name
    seen = set()
    unique = []
    for s in subreddits:
        if s["name"] not in seen:
            seen.add(s["name"])
            unique.append(s)
    return unique


def _score_and_rank(
    claude_channels: list[dict],
    reddit_results: list[dict],
) -> list[dict]:
    """Combine Claude reasoning with validation. Boost verified, demote unverified."""
    reddit_names = {r["name"].lower() for r in reddit_results}

    for ch in claude_channels:
        _compute_ice(ch)

        # Boost verified channels
        if ch.get("_verified"):
            ch["confidence"] = min(10, ch["confidence"] + 1)
            ch["ice"] = ch["impact"] * ch["confidence"] * ch["ease"]
        else:
            ch["confidence"] = max(1, ch["confidence"] - 1)
            ch["ice"] = ch["impact"] * ch["confidence"] * ch["ease"]

        # Boost Reddit channels that were found via API
        if ch.get("platform") == "reddit" and ch.get("name", "").lower() in reddit_names:
            ch["confidence"] = min(10, ch["confidence"] + 2)
            ch["ice"] = ch["impact"] * ch["confidence"] * ch["ease"]

        ch.pop("_verified", None)

    # Add Reddit discoveries not already in Claude's list
    claude_names = {ch.get("name", "").lower() for ch in claude_channels}
    for r in reddit_results:
        if r["name"].lower() not in claude_names:
            r["impact"] = 6
            r["confidence"] = 8 if r.get("subscribers", 0) > 1000 else 5
            r["ease"] = 5
            _compute_ice(r)
            claude_channels.append(r)

    return sorted(claude_channels, key=lambda c: c.get("ice", 0), reverse=True)


async def discover_channels(icp_description: str, *, niche: str = "") -> list[dict]:
    """Full channel discovery pipeline: Claude reasoning → Serper validation → Reddit search → ranked results."""
    keywords = niche.split() if niche else icp_description.split()[:5]

    # Run Claude reasoning and Reddit search in sequence
    claude_channels = await _claude_channel_reasoning(icp_description)
    reddit_results = await _search_reddit(keywords)

    # Validate via Serper
    if niche:
        claude_channels = await _validate_via_serper(claude_channels, niche)

    # Score and rank
    ranked = _score_and_rank(claude_channels, reddit_results)

    logger.info(
        "channel_discovery_complete",
        claude_suggestions=len(claude_channels),
        reddit_found=len(reddit_results),
        total_ranked=len(ranked),
    )

    return ranked
