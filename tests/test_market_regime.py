"""Tests for src/data/market_regime.py — regime classification."""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from src.data.market_regime import MarketRegime, RegimeDetector


def _make_hist(closes: list[float], vix_closes: list[float] | None = None) -> tuple:
    """Return (spy_hist, vix_hist) as pandas DataFrames."""
    spy = pd.DataFrame({"Close": closes})
    vix_closes = vix_closes or [15.0] * len(closes)
    vix = pd.DataFrame({"Close": vix_closes})
    return spy, vix


def _patch_yf(spy_closes: list[float], vix_closes: list[float]):
    """Context manager: patches yfinance.Ticker so SPY and ^VIX return given closes."""
    spy_hist, vix_hist = _make_hist(spy_closes, vix_closes)

    def fake_ticker(sym):
        t = MagicMock()
        t.history.return_value = spy_hist if sym == "SPY" else vix_hist
        return t

    return patch("src.data.market_regime.yf.Ticker", side_effect=fake_ticker)


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------

class TestRegimeClassification:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_extreme_fear_vix_above_30(self):
        # VIX=35, SPY above both SMAs → still EXTREME_FEAR
        spy_closes = [100.0] * 30 + [105.0]  # 31 days, rising
        vix_closes = [35.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "EXTREME_FEAR"
        assert regime.risk_multiplier == 0.0
        assert regime.vix == pytest.approx(35.0)

    def test_bear_vix_above_25(self):
        # VIX=27, SPY flat (above SMAs) → BEAR because VIX > 25
        spy_closes = [100.0] * 31
        vix_closes = [27.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "BEAR"
        assert regime.risk_multiplier == pytest.approx(0.5)

    def test_bear_spy_below_both_smas(self):
        # VIX=18 (below 20), but SPY has been falling → below SMA10 and SMA30
        # Build a downtrend: 30 days at 100, then drop to 80
        spy_closes = [100.0] * 30 + [80.0]
        vix_closes = [18.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "BEAR"
        assert regime.risk_multiplier == pytest.approx(0.5)

    def test_neutral_vix_above_20(self):
        # VIX=22, SPY flat (above SMAs)
        spy_closes = [100.0] * 31
        vix_closes = [22.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "NEUTRAL"
        assert regime.risk_multiplier == pytest.approx(0.8)

    def test_bull_low_vix_spy_above_smas(self):
        # VIX=15, SPY steadily rising → above both SMAs
        spy_closes = [90.0 + i * 0.5 for i in range(31)]  # 90, 90.5, ..., 105
        vix_closes = [15.0] * 31
        with _patch_yf(spy_closes, vix_closes):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "BULL"
        assert regime.risk_multiplier == pytest.approx(1.0)

    def test_fallback_on_yfinance_unavailable(self):
        with patch("src.data.market_regime.yf", None):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "NEUTRAL"
        assert regime.risk_multiplier == pytest.approx(0.8)
        assert regime.vix == pytest.approx(0.0)

    def test_fallback_on_empty_history(self):
        def fake_ticker(sym):
            t = MagicMock()
            t.history.return_value = pd.DataFrame()
            return t

        with patch("src.data.market_regime.yf.Ticker", side_effect=fake_ticker):
            regime = self.detector.get_regime(use_cache=False)
        assert regime.label == "NEUTRAL"


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

class TestRegimeCache:
    def setup_method(self):
        # Classification tests write to module-level _cache as a side effect
        # (even with use_cache=False, _fetch() always updates it).
        # Clear it so this test starts with a cold cache.
        import src.data.market_regime as mr
        mr._cache.clear()

    def test_cache_returns_same_object_within_ttl(self):
        detector = RegimeDetector()
        spy_closes = [100.0] * 31
        vix_closes = [15.0] * 31
        with _patch_yf(spy_closes, vix_closes) as mock_ticker:
            r1 = detector.get_regime(use_cache=True)
            r2 = detector.get_regime(use_cache=True)
        # yf.Ticker called once per symbol = 2 total (SPY + ^VIX), not 4
        assert mock_ticker.call_count == 2
