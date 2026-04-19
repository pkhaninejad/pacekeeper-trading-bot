"""Tests for KalshiClient."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from prediction_bot.src.api.models import PredictionMarket


def _make_kalshi_market(
    ticker="BTCUSD-24-T80000",
    title="Will BTC stay above $80k?",
    hours_offset=20,
    yes_bid=88,
    yes_ask=92,
    no_bid=8,
    no_ask=12,
    volume=50000,
    status="open",
    result=None,
    series_ticker="CRYPTO",
):
    close_time = (datetime.now(timezone.utc) + timedelta(hours=hours_offset)).isoformat()
    return {
        "ticker": ticker,
        "title": title,
        "close_time": close_time,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "volume": volume,
        "status": status,
        "result": result,
        "series_ticker": series_ticker,
    }


class TestKalshiClient:
    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        """When KALSHI_ENABLED=False, get_near_expiry_markets returns []."""
        from prediction_bot.src.api.kalshi_client import KalshiClient
        from prediction_bot.src.config.settings import PredictionBotSettings

        settings = PredictionBotSettings(KALSHI_ENABLED=False)
        async with KalshiClient(settings=settings) as client:
            result = await client.get_near_expiry_markets()
        assert result == []

    def test_price_extraction_from_cents(self):
        """Kalshi prices in cents (0-100) converted to dollars (0-1)."""
        from prediction_bot.src.api.kalshi_client import _parse_kalshi_market

        raw = _make_kalshi_market(yes_bid=88, yes_ask=92, no_bid=8, no_ask=12)
        market = _parse_kalshi_market(raw)
        assert market is not None
        assert abs(market.yes_price - 0.90) < 0.01
        assert abs(market.no_price - 0.10) < 0.01

    def test_category_from_series(self):
        """Series ticker prefix maps to category."""
        from prediction_bot.src.api.kalshi_client import _parse_kalshi_market

        crypto_market = _make_kalshi_market(series_ticker="CRYPTO")
        m = _parse_kalshi_market(crypto_market)
        assert m.category == "crypto"

        politics_market = _make_kalshi_market(series_ticker="ELECTIONS")
        m2 = _parse_kalshi_market(politics_market)
        assert m2.category == "politics"

    @pytest.mark.asyncio
    async def test_resolution_detection_settled(self):
        """Settled market with result returns resolved=True."""
        from prediction_bot.src.api.kalshi_client import KalshiClient
        from prediction_bot.src.config.settings import PredictionBotSettings

        settings = PredictionBotSettings(KALSHI_ENABLED=True, KALSHI_API_KEY="test")
        settled = _make_kalshi_market(status="settled", result="yes")

        async with KalshiClient(settings=settings) as client:
            client._token = "fake-token"
            with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = settled
                status = await client.get_market_status("BTCUSD-T80000")

        assert status["resolved"] is True
        assert status["winner"] == "YES"

    @pytest.mark.asyncio
    async def test_near_expiry_filters_time(self):
        """Markets outside the expiry window are excluded."""
        from prediction_bot.src.api.kalshi_client import KalshiClient
        from prediction_bot.src.config.settings import PredictionBotSettings

        settings = PredictionBotSettings(KALSHI_ENABLED=True, KALSHI_API_KEY="test")
        inside = _make_kalshi_market(ticker="IN", hours_offset=10)
        outside = _make_kalshi_market(ticker="OUT", hours_offset=100)

        async with KalshiClient(settings=settings) as client:
            client._token = "fake-token"
            with patch.object(client, "_get_markets_raw", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ([inside, outside], None)
                markets = await client.get_near_expiry_markets(hours=48, min_volume=0)

        ids = [m.id for m in markets]
        assert "IN" in ids
        assert "OUT" not in ids
