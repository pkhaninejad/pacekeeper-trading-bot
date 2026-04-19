"""Market scanner — filters and ranks MarketCandidate list from both platforms."""
from __future__ import annotations

import logging
import math

from prediction_bot.src.api.models import MarketCandidate, PredictionMarket
from prediction_bot.src.config.settings import PredictionBotSettings

logger = logging.getLogger(__name__)


async def scan_markets(
    polymarket,
    kalshi,
    settings: PredictionBotSettings,
) -> list[MarketCandidate]:
    """Scan both platforms and return ranked MarketCandidate list (best first, max 50)."""
    raw: list[PredictionMarket] = []

    if polymarket:
        try:
            poly_markets = await polymarket.get_near_expiry_markets(
                hours=settings.EXPIRY_WINDOW_HOURS,
                min_liquidity=settings.MIN_LIQUIDITY,
            )
            raw.extend(poly_markets)
            logger.info("Polymarket: %d near-expiry markets fetched", len(poly_markets))
        except Exception as e:
            logger.warning("Polymarket scan error: %s", e)

    if kalshi:
        try:
            kalshi_markets = await kalshi.get_near_expiry_markets(
                hours=settings.EXPIRY_WINDOW_HOURS,
                min_volume=settings.MIN_LIQUIDITY,
            )
            raw.extend(kalshi_markets)
            logger.info("Kalshi: %d near-expiry markets fetched", len(kalshi_markets))
        except Exception as e:
            logger.warning("Kalshi scan error: %s", e)

    candidates: list[MarketCandidate] = []
    for market in raw:
        if market.category not in settings.ENABLED_CATEGORIES:
            continue
        if market.liquidity < settings.MIN_LIQUIDITY:
            continue

        best_side = "YES" if market.yes_price >= market.no_price else "NO"
        best_price = market.yes_price if best_side == "YES" else market.no_price

        if not (settings.HIGH_PROB_MIN <= best_price <= settings.HIGH_PROB_MAX):
            continue

        candidates.append(MarketCandidate(
            market=market,
            best_side=best_side,
            market_price=best_price,
        ))

    def _score(c: MarketCandidate) -> float:
        return (1.0 - c.market_price) * math.log(c.market.liquidity + 1)

    candidates.sort(key=_score, reverse=True)
    return candidates[:50]
