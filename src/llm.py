import time

import anthropic
import structlog

from src.config import settings

logger = structlog.get_logger()

MODELS = {
    "opus": "claude-opus-4-20250514",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-4-20250414",
}

# Approximate cost per 1K tokens (USD) — input / output
COST_PER_1K = {
    "claude-opus-4-20250514": (0.015, 0.075),
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-4-20250414": (0.00025, 0.00125),
}

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def call_claude(
    *,
    model_tier: str = "sonnet",
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> tuple[str, float]:
    """Call Claude and return (response_text, cost_usd).

    model_tier: one of "opus", "sonnet", "haiku" — maps to actual model IDs.
    """
    model_id = MODELS.get(model_tier, MODELS["sonnet"])

    t0 = time.monotonic()
    response = await _client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    elapsed = time.monotonic() - t0

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost_in, cost_out = COST_PER_1K.get(model_id, (0.003, 0.015))
    cost_usd = (input_tokens * cost_in + output_tokens * cost_out) / 1000.0

    logger.info(
        "claude_call",
        model=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 6),
        elapsed_s=round(elapsed, 2),
    )

    text = response.content[0].text if response.content else ""
    return text, cost_usd
