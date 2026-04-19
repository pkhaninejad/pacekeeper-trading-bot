"""Tests for src/data/prediction_markets.py."""
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest


# ---------------------------------------------------------------------------
# MarketProb
# ---------------------------------------------------------------------------

class TestMarketProb:
    def test_fields(self):
        from src.data.prediction_markets import MarketProb
        mp = MarketProb(
            source="polymarket",
            event="Fed cuts May 2025",
            ticker=None,
            yes_prob=0.72,
            volume_usd=2_100_000,
            url="https://polymarket.com/event/fed-cuts",
            fetched_at=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        )
        assert mp.source == "polymarket"
        assert mp.yes_prob == 0.72
        assert mp.ticker is None
        assert mp.volume_usd == 2_100_000


# ---------------------------------------------------------------------------
# Polymarket fetcher
# ---------------------------------------------------------------------------

class TestFetchPolymarketMacro:
    def test_returns_market_prob_on_success(self):
        """Returns list of MarketProb for each macro entry with a polymarket_slug."""
        from src.data.prediction_markets import _fetch_polymarket_macro

        poly_response = {
            "markets": [
                {
                    "outcomePrices": '["0.72", "0.28"]',
                    "volume": "2100000.00",
                    "conditionId": "abc123",
                }
            ]
        }

        with patch("src.data.prediction_markets.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = poly_response

            results = _fetch_polymarket_macro([
                {"label": "Fed cuts May 2025", "polymarket_slug": "fed-cuts-may-2025", "kalshi_series": None}
            ])

        assert len(results) == 1
        mp = results[0]
        assert mp.source == "polymarket"
        assert mp.event == "Fed cuts May 2025"
        assert mp.ticker is None
        assert abs(mp.yes_prob - 0.72) < 0.001
        assert mp.volume_usd == 2_100_000

    def test_skips_entry_without_slug(self):
        """Entries with null polymarket_slug are skipped."""
        from src.data.prediction_markets import _fetch_polymarket_macro

        results = _fetch_polymarket_macro([
            {"label": "CPI above 3%", "polymarket_slug": None, "kalshi_series": None}
        ])
        assert results == []

    def test_returns_empty_on_http_error(self):
        """HTTP errors return empty list without raising."""
        from src.data.prediction_markets import _fetch_polymarket_macro

        with patch("src.data.prediction_markets.requests.get") as mock_get:
            mock_get.return_value.status_code = 500
            mock_get.return_value.raise_for_status.side_effect = Exception("500")

            results = _fetch_polymarket_macro([
                {"label": "Fed cuts May 2025", "polymarket_slug": "fed-cuts-may-2025", "kalshi_series": None}
            ])

        assert results == []


# ---------------------------------------------------------------------------
# Kalshi fetcher
# ---------------------------------------------------------------------------

class TestFetchKalshiTicker:
    def test_returns_market_prob_on_success(self):
        """Returns MarketProb list when Kalshi API responds with matching markets."""
        from src.data.prediction_markets import _fetch_kalshi_ticker

        kalshi_response = {
            "markets": [
                {
                    "title": "NVDA earnings beat Q1 2025",
                    "yes_ask": 0.61,
                    "volume": 45000,
                    "ticker": "NVDA-EARN-Q1-2025",
                }
            ]
        }

        with patch("src.data.prediction_markets.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = kalshi_response

            results = _fetch_kalshi_ticker(
                ticker="NVDA",
                entries=[{"label": "NVDA earnings beat Q1 2025", "kalshi_series": None, "discovery_keywords": ["nvidia", "earnings"]}],
                api_key="test-key",
            )

        assert len(results) == 1
        mp = results[0]
        assert mp.source == "kalshi"
        assert mp.ticker == "NVDA"
        assert abs(mp.yes_prob - 0.61) < 0.001
        assert mp.volume_usd == 45000

    def test_returns_empty_without_api_key(self):
        """Skips Kalshi silently when api_key is empty."""
        from src.data.prediction_markets import _fetch_kalshi_ticker

        results = _fetch_kalshi_ticker(
            ticker="NVDA",
            entries=[{"label": "NVDA earnings beat Q1 2025", "kalshi_series": None, "discovery_keywords": ["nvidia"]}],
            api_key="",
        )
        assert results == []

    def test_returns_empty_on_http_error(self):
        """HTTP errors return empty list without raising."""
        from src.data.prediction_markets import _fetch_kalshi_ticker

        with patch("src.data.prediction_markets.requests.get") as mock_get:
            mock_get.return_value.status_code = 401
            mock_get.return_value.raise_for_status.side_effect = Exception("401 Unauthorized")

            results = _fetch_kalshi_ticker(
                ticker="NVDA",
                entries=[{"label": "NVDA earnings beat", "kalshi_series": None, "discovery_keywords": ["nvidia"]}],
                api_key="bad-key",
            )
        assert results == []


# ---------------------------------------------------------------------------
# Cache + public function
# ---------------------------------------------------------------------------

class TestGetPredictionMarketContext:
    def setup_method(self):
        from src.data import prediction_markets
        prediction_markets._cache.clear()

    def test_returns_macro_and_ticker_keys(self):
        """Result contains 'macro' key and one key per watchlist ticker."""
        from src.data.prediction_markets import get_prediction_market_context, MarketProb

        macro_prob = MarketProb(
            source="polymarket", event="Fed cuts", ticker=None,
            yes_prob=0.7, volume_usd=1_000_000,
            url="https://polymarket.com/x", fetched_at=datetime.now(timezone.utc),
        )
        nvda_prob = MarketProb(
            source="kalshi", event="NVDA beat", ticker="NVDA",
            yes_prob=0.6, volume_usd=50_000,
            url="https://kalshi.com/x", fetched_at=datetime.now(timezone.utc),
        )

        with patch("src.data.prediction_markets._fetch_polymarket_macro", return_value=[macro_prob]), \
             patch("src.data.prediction_markets._fetch_kalshi_ticker", return_value=[nvda_prob]), \
             patch("src.data.prediction_markets._settings") as mock_settings:
            mock_settings.KALSHI_API_KEY = "test-key"
            mock_settings.PREDICTION_MARKETS_CACHE_TTL = 900
            result = get_prediction_market_context(["NVDA"])

        assert "macro" in result
        assert "NVDA" in result
        assert result["macro"][0].event == "Fed cuts"
        assert result["NVDA"][0].event == "NVDA beat"

    def test_returns_cached_result_within_ttl(self):
        """Second call within TTL does not re-fetch."""
        from src.data.prediction_markets import get_prediction_market_context

        with patch("src.data.prediction_markets._fetch_polymarket_macro", return_value=[]) as poly_mock, \
             patch("src.data.prediction_markets._fetch_kalshi_ticker", return_value=[]), \
             patch("src.data.prediction_markets._settings") as mock_settings:
            mock_settings.KALSHI_API_KEY = "test-key"
            mock_settings.PREDICTION_MARKETS_CACHE_TTL = 900
            get_prediction_market_context(["NVDA"])
            get_prediction_market_context(["NVDA"])

        assert poly_mock.call_count == 1

    def test_empty_result_when_all_fetchers_fail(self):
        """Returns dict with empty lists when both fetchers return empty."""
        from src.data.prediction_markets import get_prediction_market_context

        with patch("src.data.prediction_markets._fetch_polymarket_macro", return_value=[]), \
             patch("src.data.prediction_markets._fetch_kalshi_ticker", return_value=[]), \
             patch("src.data.prediction_markets._settings") as mock_settings:
            mock_settings.KALSHI_API_KEY = ""
            mock_settings.PREDICTION_MARKETS_CACHE_TTL = 900
            result = get_prediction_market_context(["NVDA"])

        assert result["macro"] == []
        assert result.get("NVDA", []) == []
