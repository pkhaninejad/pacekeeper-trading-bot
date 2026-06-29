"""Market scanner — filters and ranks MarketCandidate list from all platforms."""
from __future__ import annotations

import logging
import math

from prediction_bot.src.api.models import MarketCandidate, PredictionMarket
from prediction_bot.src.config.settings import PredictionBotSettings

logger = logging.getLogger(__name__)


async def scan_markets(
    clients: list,
    settings: PredictionBotSettings,
) -> list[MarketCandidate]:
    """Scan all platform clients and return ranked MarketCandidate list (best first, max 50)."""
    raw: list[PredictionMarket] = []

    for client in clients:
        name = getattr(client, "platform", type(client).__name__)
        try:
            markets = await client.get_near_expiry_markets(
                hours=settings.EXPIRY_WINDOW_HOURS,
                min_liquidity=settings.MIN_LIQUIDITY,
            )
            raw.extend(markets)
            logger.info("%s: %d near-expiry markets fetched", name, len(markets))
        except Exception as e:
            logger.warning("%s scan error: %s", name, e)

    candidates: list[MarketCandidate] = []
    for market in raw:
        if market.category not in settings.ENABLED_CATEGORIES:
            continue
        if market.liquidity < settings.MIN_LIQUIDITY:
            continue

        candidate = _apply_strategy(market, settings)
        if candidate is not None:
            candidates.append(candidate)

    def _score(c: MarketCandidate) -> float:
        return (1.0 - c.market_price) * math.log(c.market.liquidity + 1)

    candidates.sort(key=_score, reverse=True)
    return candidates[:50]


def _apply_strategy(
    market: PredictionMarket,
    settings: PredictionBotSettings,
) -> MarketCandidate | None:
    """Return a MarketCandidate for this market under the active strategy, or None to skip."""
    high_side = "YES" if market.yes_price >= market.no_price else "NO"
    high_price = market.yes_price if high_side == "YES" else market.no_price

    if not (settings.HIGH_PROB_MIN <= high_price <= settings.HIGH_PROB_MAX):
        return None

    if settings.BET_STRATEGY == "contrarian":
        best_side = "NO" if high_side == "YES" else "YES"
        best_price = market.no_price if best_side == "NO" else market.yes_price
    else:
        best_side = high_side
        best_price = high_price
        if settings.BET_STRATEGY == "min_rr":
            rr = (1.0 - best_price) / best_price if best_price > 0 else 0.0
            if rr < settings.MIN_RR_RATIO:
                return None

    return MarketCandidate(
        market=market,
        best_side=best_side,
        market_price=best_price,
    )
