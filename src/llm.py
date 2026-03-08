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

COST_PER_1K = {
    "claude-opus-4-20250514": (0.015, 0.075),
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-4-20250414": (0.00025, 0.00125),
}

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.get("ANTHROPIC_API_KEY"))
    return _client


async def call_claude(
    *,
    model_tier: str = "sonnet",
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> tuple[str, float]:
    """Call Claude and return (response_text, cost_usd).

    Automatically uses streaming for large requests (max_tokens > 8192)
    to avoid the 10-minute timeout on non-streaming requests.
    """
    model_id = MODELS.get(model_tier, MODELS["sonnet"])
    use_streaming = max_tokens > 8192

    t0 = time.monotonic()

    if use_streaming:
        text, input_tokens, output_tokens = await _call_streaming(
            model_id, system, user, max_tokens, temperature
        )
    else:
        response = await _get_client().messages.create(
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

    elapsed = time.monotonic() - t0

    cost_in, cost_out = COST_PER_1K.get(model_id, (0.003, 0.015))
    cost_usd = (input_tokens * cost_in + output_tokens * cost_out) / 1000.0

    logger.info(
        "claude_call",
        model=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 6),
        elapsed_s=round(elapsed, 2),
        streaming=use_streaming,
    )

    return text, cost_usd


async def _call_streaming(
    model_id: str, system: str, user: str, max_tokens: int, temperature: float
) -> tuple[str, int, int]:
    """Stream a Claude response, collecting text and token counts."""
    chunks = []
    input_tokens = 0
    output_tokens = 0

    async with _get_client().messages.stream(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        async for event in stream:
            if hasattr(event, "type"):
                if event.type == "content_block_delta" and hasattr(event, "delta"):
                    if hasattr(event.delta, "text"):
                        chunks.append(event.delta.text)
                elif event.type == "message_delta" and hasattr(event, "usage"):
                    output_tokens = getattr(event.usage, "output_tokens", 0)
                elif event.type == "message_start" and hasattr(event, "message"):
                    usage = getattr(event.message, "usage", None)
                    if usage:
                        input_tokens = getattr(usage, "input_tokens", 0)

    text = "".join(chunks)
    return text, input_tokens, output_tokens
