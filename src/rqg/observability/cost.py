"""Token cost estimation.

Prices are USD per million tokens, first-party Anthropic API list prices for prompts up to
100K tokens (checked 2026-11). Update ``PRICING`` when prices change; unknown models cost 0
and are reported as such.
"""

from __future__ import annotations

PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "mock-support-v1": (0.0, 0.0),
    "mock-judge-v1": (0.0, 0.0),
}


def price_for(model: str) -> tuple[float, float] | None:
    if model in PRICING:
        return PRICING[model]
    for name, p in PRICING.items():  # tolerate provider-returned ids with suffixes
        if model.startswith(name):
            return p
    return None


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated cost of one call; 0.0 for unknown models."""
    p = price_for(model)
    if p is None:
        return 0.0
    return (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000


def estimate_cost_with(
    model_prices: tuple[float, float], input_tokens: int, output_tokens: int
) -> float:
    return (input_tokens * model_prices[0] + output_tokens * model_prices[1]) / 1_000_000
