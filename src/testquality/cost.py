"""Cost estimation. Heuristic token count (no network) unless an exact count is supplied."""

from __future__ import annotations

CHARS_PER_TOKEN = 3.3  # conservative for Python source


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


def call_cost(model: str, input_tokens: int, output_tokens: int, pricing: dict) -> float:
    p = pricing[model]
    return input_tokens * p["input"] / 1e6 + output_tokens * p["output"] / 1e6


def usage_cost(model: str, usage: dict, pricing: dict) -> float:
    """Actual cost from a logged usage record (uncached input + output; thinking is output)."""
    return call_cost(
        model, usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0, pricing
    )
