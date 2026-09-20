"""Token pricing for logs that carry usage but no cost (Claude Code does not).

USD per million tokens, Anthropic first-party API list prices. The result is an
estimate: a subscription session costs nothing per token, and partner clouds
price differently - which is why the report labels it ``cost_estimated``.
"""

from __future__ import annotations

__all__ = ["price_for", "usage_cost"]

# (model id prefix, input, output, cache read). First match wins, so the more
# specific prefix comes first. Cache writes are billed at 1.25x input.
_PRICES: tuple[tuple[str, float, float, float], ...] = (
    ("claude-fable-5-1", 10.0, 50.0, 0.25),
    ("claude-mythos-5-1", 10.0, 50.0, 0.25),
    ("claude-fable", 10.0, 50.0, 1.0),
    ("claude-mythos", 10.0, 50.0, 1.0),
    ("claude-opus-4-1", 15.0, 75.0, 1.5),
    ("claude-opus-4-0", 15.0, 75.0, 1.5),
    ("claude-opus-4-2", 15.0, 75.0, 1.5),  # dated ids of Opus 4: claude-opus-4-20250514
    ("claude-3-opus", 15.0, 75.0, 1.5),
    ("claude-opus", 5.0, 25.0, 0.5),
    ("claude-sonnet-5", 2.0, 10.0, 0.2),
    ("claude-sonnet", 3.0, 15.0, 0.3),
    ("claude-3-7-sonnet", 3.0, 15.0, 0.3),
    ("claude-3-5-sonnet", 3.0, 15.0, 0.3),
    ("claude-3-5-haiku", 0.8, 4.0, 0.08),
    ("claude-3-haiku", 0.25, 1.25, 0.03),
    ("claude-haiku", 1.0, 5.0, 0.1),
)
_CACHE_WRITE_MULTIPLIER = 1.25


def price_for(model: str | None) -> tuple[float, float, float] | None:
    """(input, output, cache read) per million tokens, or None for an unknown model."""
    name = (model or "").strip().lower()
    for prefix, *prices in _PRICES:
        if name.startswith(prefix):
            return tuple(prices)  # type: ignore[return-value]
    return None


def usage_cost(model: str | None, *, input_tokens: int = 0, output_tokens: int = 0,
               cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> float:
    """Estimated USD for one usage delta; 0.0 when the model is not priced."""
    prices = price_for(model)
    if prices is None:
        return 0.0
    price_in, price_out, price_cache_read = prices
    total = (
        input_tokens * price_in
        + cache_write_tokens * price_in * _CACHE_WRITE_MULTIPLIER
        + output_tokens * price_out
        + cache_read_tokens * price_cache_read
    )
    return round(total / 1_000_000, 6)
