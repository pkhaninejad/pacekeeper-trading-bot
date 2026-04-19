"""Tests for PolymarketClient."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from prediction_bot.src.api.models import PredictionMarket


def _make_raw_market(
    id="abc123",
    question="Will BTC stay above $80k?",
    end_date_offset_hours=24,
    yes_price=0.92,
    volume=150000,
    liquidity=50000,
    closed=False,
    tags=None,
):
    end_dt = datetime.now(timezone.utc) + timedelta(hours=end_date_offset_hours)
    return {
        "conditionId": id,
        "question": question,
        "endDate": end_dt.isoformat(),
        "outcomePrices": f'["{yes_price}", "{round(1-yes_price, 2)}"]',
        "volume24hr": volume,
        "liquidity": liquidity,
        "closed": closed,
        "slug": "will-btc-stay-above-80k",
        "tags": tags or [{"label": "Crypto"}],
    }


class TestPolymarketClient:
    @pytest.mark.asyncio
    async def test_get_active_markets_parses_models(self):
        """Returns list of PredictionMarket from raw API response."""
        from prediction_bot.src.api.polymarket_client import PolymarketClient

        raw = {"markets": [_make_raw_market()]}

        async with PolymarketClient() as client:
            with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = raw
                markets = await client.get_active_markets(limit=10)

        assert len(markets) == 1
        m = markets[0]
        assert isinstance(m, PredictionMarket)
        assert m.platform == "polymarket"
        assert abs(m.yes_price - 0.92) < 0.001

    def test_price_extraction_from_json_string(self):
        """outcomePrices JSON string parsed correctly."""
        from prediction_bot.src.api.polymarket_client import _parse_outcome_prices

        yes, no = _parse_outcome_prices('["0.85", "0.15"]')
        assert abs(yes - 0.85) < 0.001
        assert abs(no - 0.15) < 0.001

    @pytest.mark.asyncio
    async def test_near_expiry_filters_by_time(self):
        """get_near_expiry_markets only returns markets within the window."""
        from prediction_bot.src.api.polymarket_client import PolymarketClient

        inside = _make_raw_market(id="in", end_date_offset_hours=20)
        outside = _make_raw_market(id="out", end_date_offset_hours=100)
        raw = {"markets": [inside, outside]}

        async with PolymarketClient() as client:
            with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = raw
                markets = await client.get_near_expiry_markets(hours=48, min_liquidity=0)

        ids = [m.id for m in markets]
        assert "in" in ids
        assert "out" not in ids

    @pytest.mark.asyncio
    async def test_resolution_detection(self):
        """Closed market with settled prices detected as resolved."""
        from prediction_bot.src.api.polymarket_client import PolymarketClient

        raw_resolved = {
            "conditionId": "res1",
            "closed": True,
            "outcomePrices": '["1.0", "0.0"]',
            "question": "Test?",
            "endDate": datetime.now(timezone.utc).isoformat(),
            "volume24hr": 0,
            "liquidity": 0,
            "slug": "test",
            "tags": [],
        }

        async with PolymarketClient() as client:
            with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = raw_resolved
                status = await client.get_market_status("res1")

        assert status["resolved"] is True
        assert status["winner"] == "YES"
