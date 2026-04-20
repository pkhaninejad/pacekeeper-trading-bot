"""Tests for scan_markets()."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
import pytest

from prediction_bot.src.api.models import PredictionMarket, MarketCandidate
from prediction_bot.src.config.settings import PredictionBotSettings


def _market(
    id="m1",
    platform="polymarket",
    question="Will BTC hit $90k?",
    category="crypto",
    hours_offset=20,
    yes_price=0.92,
    liquidity=5000.0,
):
    return PredictionMarket(
        id=id,
        platform=platform,
        question=question,
        category=category,
        end_date=datetime.now(timezone.utc) + timedelta(hours=hours_offset),
        yes_price=yes_price,
        no_price=round(1 - yes_price, 2),
        liquidity=liquidity,
    )


@pytest.fixture
def settings():
    return PredictionBotSettings(
        HIGH_PROB_MIN=0.80,
        HIGH_PROB_MAX=0.97,
        MIN_LIQUIDITY=1000.0,
        EXPIRY_WINDOW_HOURS=48,
        ENABLED_CATEGORIES=["crypto", "sports", "politics"],
    )


class TestScanMarkets:
    @pytest.mark.asyncio
    async def test_filters_low_liquidity(self, settings):
        from prediction_bot.src.bot.scanner import scan_markets

        low_liq = _market(id="low", liquidity=500.0)
        ok = _market(id="ok", liquidity=2000.0)

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[low_liq, ok])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        ids = [c.market.id for c in result]
        assert "ok" in ids
        assert "low" not in ids

    @pytest.mark.asyncio
    async def test_filters_price_below_range(self, settings):
        from prediction_bot.src.bot.scanner import scan_markets

        cheap = _market(id="cheap", yes_price=0.60)
        good = _market(id="good", yes_price=0.90)

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[cheap, good])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        ids = [c.market.id for c in result]
        assert "good" in ids
        assert "cheap" not in ids

    @pytest.mark.asyncio
    async def test_filters_price_above_range(self, settings):
        from prediction_bot.src.bot.scanner import scan_markets

        too_high = _market(id="high", yes_price=0.99)
        good = _market(id="good", yes_price=0.91)

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[too_high, good])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        ids = [c.market.id for c in result]
        assert "good" in ids
        assert "high" not in ids

    @pytest.mark.asyncio
    async def test_best_side_yes(self, settings):
        from prediction_bot.src.bot.scanner import scan_markets

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[_market(yes_price=0.92)])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        assert result[0].best_side == "YES"
        assert abs(result[0].market_price - 0.92) < 0.001

    @pytest.mark.asyncio
    async def test_best_side_no(self, settings):
        from prediction_bot.src.bot.scanner import scan_markets

        m = _market(yes_price=0.08)  # no_price = 0.92
        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[m])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        assert len(result) == 1
        assert result[0].best_side == "NO"
        assert abs(result[0].market_price - 0.92) < 0.001

    @pytest.mark.asyncio
    async def test_filters_disabled_category(self, settings):
        from prediction_bot.src.bot.scanner import scan_markets

        s = PredictionBotSettings(
            HIGH_PROB_MIN=0.80, HIGH_PROB_MAX=0.97, MIN_LIQUIDITY=0,
            EXPIRY_WINDOW_HOURS=48, ENABLED_CATEGORIES=["crypto"],
        )
        sports_market = _market(id="sports", category="sports")
        crypto_market = _market(id="crypto", category="crypto")

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[sports_market, crypto_market])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, s)
        ids = [c.market.id for c in result]
        assert "crypto" in ids
        assert "sports" not in ids

    @pytest.mark.asyncio
    async def test_ranked_by_edge_potential(self, settings):
        from prediction_bot.src.bot.scanner import scan_markets

        high_edge = _market(id="hedge", yes_price=0.82, liquidity=10000)
        low_edge = _market(id="ledge", yes_price=0.95, liquidity=1000)

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[low_edge, high_edge])
        kalshi_mock = AsyncMock()
        kalshi_mock.get_near_expiry_markets = AsyncMock(return_value=[])

        result = await scan_markets(poly_mock, kalshi_mock, settings)
        assert result[0].market.id == "hedge"

    @pytest.mark.asyncio
    async def test_single_platform_kalshi_none(self, settings):
        from prediction_bot.src.bot.scanner import scan_markets

        poly_mock = AsyncMock()
        poly_mock.get_near_expiry_markets = AsyncMock(return_value=[_market()])

        result = await scan_markets(poly_mock, None, settings)
        assert len(result) == 1
