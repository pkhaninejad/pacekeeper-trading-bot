"""Prompt templates for the LLM evaluator."""
from __future__ import annotations
from datetime import UTC, datetime

from prediction_bot.src.api.models import MarketCandidate

SYSTEM_PROMPT = """You are a prediction market analyst. For each market, estimate the TRUE probability of YES based on:
1. The market question and what it takes to resolve YES
2. The current market price (crowd wisdom)
3. Any external data provided
4. Your knowledge up to your training cutoff

Be calibrated. Only flag edge when you have genuine reasons. Respond with a JSON array only.
For each market: {"market_id": "...", "true_probability": 0.0-1.0, "confidence": 0.0-1.0, "reasoning": "...", "recommended_side": "YES"|"NO"|"SKIP"}"""


def build_user_prompt(candidates: list[MarketCandidate]) -> str:
    lines = ["=== MARKETS TO EVALUATE ===\n"]
    now = datetime.now(UTC)
    for i, c in enumerate(candidates, 1):
        hours_left = max(0, (c.market.end_date - now).total_seconds() / 3600)
        lines.append(f"Market {i} (id: {c.market.id})")
        lines.append(f'  Question: "{c.market.question}"')
        lines.append(f"  Platform: {c.market.platform} | Category: {c.market.category}")
        lines.append(f"  Expires in: {hours_left:.1f}h")
        lines.append(f"  YES price: ${c.market.yes_price:.2f} | NO price: ${c.market.no_price:.2f}")
        lines.append(f"  Our best side: {c.best_side} @ ${c.market_price:.2f}")
        lines.append(f"  Liquidity: ${c.market.liquidity:,.0f}")
        if c.external_data:
            for k, v in c.external_data.items():
                lines.append(f"  {k.title()} data: {v}")
        lines.append("")
    lines.append("Respond with JSON array only. SKIP when edge < 2%.")
    return "\n".join(lines)
