"""Tests for src/data/market_regime.py."""

from unittest.mock import patch
import pandas as pd
from src.data.market_regime import get_regime, _classify, _CACHE
from src.api.models import RegimeResult


class TestClassify:
    def test_bull(self):
        # SPY 5% above EMA200, VIX 15 → BULL
        result = _classify(spy_vs_200ema=5.0, vix=15.0)
        assert result.regime == "BULL"
        assert result.position_size_multiplier == 1.0

    def test_neutral_vix_range(self):
        # SPY 5% above EMA200 but VIX 25 → NEUTRAL
        result = _classify(spy_vs_200ema=5.0, vix=25.0)
        assert result.regime == "NEUTRAL"
        assert result.position_size_multiplier == 0.75

    def test_neutral_spy_within_band(self):
        # SPY within ±2% of EMA200, VIX 15 → NEUTRAL
        result = _classify(spy_vs_200ema=1.0, vix=15.0)
        assert result.regime == "NEUTRAL"
        assert result.position_size_multiplier == 0.75

    def test_bear(self):
        # SPY 5% below EMA200, VIX 32 → BEAR
        result = _classify(spy_vs_200ema=-5.0, vix=32.0)
        assert result.regime == "BEAR"
        assert result.position_size_multiplier == 0.50

    def test_extreme_fear(self):
        # VIX > 40 → EXTREME_FEAR regardless of SPY
        result = _classify(spy_vs_200ema=5.0, vix=45.0)
        assert result.regime == "EXTREME_FEAR"
        assert result.position_size_multiplier == 0.0

    def test_extreme_fear_overrides_bull_spy(self):
        result = _classify(spy_vs_200ema=10.0, vix=41.0)
        assert result.regime == "EXTREME_FEAR"


class TestGetRegime:
    def setup_method(self):
        _CACHE.clear()

    def _make_spy_df(self, last_close: float) -> pd.DataFrame:
        """210 rows — enough for a 200-day EMA. All at last_close."""
        return pd.DataFrame({"Close": [last_close] * 210})

    def _make_vix_df(self, vix_close: float) -> pd.DataFrame:
        return pd.DataFrame({"Close": [vix_close]})

    def test_get_regime_returns_regime_result(self):
        spy_df = self._make_spy_df(500.0)
        vix_df = self._make_vix_df(15.0)
        with patch("src.data.market_regime._fetch_spy", return_value=spy_df), \
             patch("src.data.market_regime._fetch_vix", return_value=vix_df):
            result = get_regime()
        assert isinstance(result, RegimeResult)

    def test_get_regime_caches_result(self):
        spy_df = self._make_spy_df(500.0)
        vix_df = self._make_vix_df(15.0)
        with patch("src.data.market_regime._fetch_spy", return_value=spy_df) as mock_spy, \
             patch("src.data.market_regime._fetch_vix", return_value=vix_df):
            get_regime()
            get_regime()
        # Second call should use cache — fetch called only once
        assert mock_spy.call_count == 1

    def test_get_regime_fallback_on_yfinance_failure(self):
        with patch("src.data.market_regime._fetch_spy", side_effect=Exception("network error")), \
             patch("src.data.market_regime._fetch_vix", side_effect=Exception("network error")):
            result = get_regime()
        assert result.regime == "NEUTRAL"
        assert result.position_size_multiplier == 1.0
