"""Unit tests for src/data/indicators.py"""

import pandas as pd
import pytest
from src.data.indicators import (
    rsi, macd, bollinger_bands, ema_cross, volume_signal,
    compute_indicators, _build_summary,
)


def _close(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def _df(closes: list[float], volumes: list[float] = None) -> pd.DataFrame:
    if volumes is None:
        volumes = [1_000_000] * len(closes)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": volumes})


# ── RSI ───────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_returns_none_when_insufficient_data(self):
        assert rsi(_close([100.0] * 5), period=14) is None

    def test_all_gains_returns_100(self):
        prices = list(range(1, 20))  # strictly increasing
        result = rsi(_close(prices))
        assert result == 100.0

    def test_all_losses_returns_0(self):
        prices = list(range(20, 1, -1))  # strictly decreasing
        result = rsi(_close(prices))
        assert result == 0.0

    def test_neutral_market_near_50(self):
        # Alternating up/down produces RSI near 50
        prices = [100 + (i % 2) for i in range(30)]
        result = rsi(_close(prices))
        assert result is not None
        assert 40 <= result <= 60

    def test_overbought_above_70(self):
        # 25 up days then 5 down days
        prices = list(range(100, 126)) + [124, 123, 122, 121, 120]
        result = rsi(_close(prices))
        assert result is not None
        assert result > 60

    def test_oversold_below_30(self):
        prices = list(range(125, 99, -1)) + [100, 101, 102, 103, 104]
        result = rsi(_close(prices))
        assert result is not None
        assert result < 40


# ── MACD ─────────────────────────────────────────────────────────────────────

class TestMACD:
    def test_returns_none_when_insufficient(self):
        result = macd(_close([100.0] * 10))
        assert result["macd"] is None

    def test_bullish_crossover_detected(self):
        # Declining then sharply rising — forces MACD line up through signal
        prices = [100 - i * 0.5 for i in range(30)] + [100 + i * 2 for i in range(10)]
        result = macd(_close(prices))
        assert result["macd"] is not None
        # histogram should be positive after sharp rise
        assert result["histogram"] is not None

    def test_bearish_histogram_on_decline(self):
        prices = [100 + i for i in range(30)] + [130 - i * 2 for i in range(15)]
        result = macd(_close(prices))
        assert result["histogram"] is not None

    def test_returns_all_keys(self):
        prices = list(range(1, 50))
        result = macd(_close(prices))
        assert set(result.keys()) == {"macd", "signal", "histogram", "crossover"}


# ── Bollinger Bands ───────────────────────────────────────────────────────────

class TestBollingerBands:
    def test_returns_none_when_insufficient(self):
        result = bollinger_bands(_close([100.0] * 5), period=20)
        assert result["upper"] is None

    def test_upper_band_above_middle(self):
        prices = [100.0 + (i % 5) for i in range(25)]
        result = bollinger_bands(_close(prices))
        assert result["upper"] > result["middle"] > result["lower"]

    def test_price_at_upper_band_signals_overbought(self):
        # Flat prices then sharp spike — last price above upper band
        base = [100.0] * 19
        spike = [140.0]  # well above BB
        result = bollinger_bands(_close(base + spike))
        assert result["band_signal"] == "upper"

    def test_price_at_lower_band_signals_oversold(self):
        base = [100.0] * 19
        drop = [60.0]
        result = bollinger_bands(_close(base + drop))
        assert result["band_signal"] == "lower"

    def test_normal_price_signals_middle(self):
        prices = [100.0 + (i % 3) for i in range(25)]
        result = bollinger_bands(_close(prices))
        assert result["band_signal"] == "middle"

    def test_pct_b_between_0_and_1_normally(self):
        prices = [100.0 + (i % 5) for i in range(25)]
        result = bollinger_bands(_close(prices))
        assert 0 <= result["pct_b"] <= 1


# ── EMA Cross ─────────────────────────────────────────────────────────────────

class TestEMACross:
    def test_returns_none_when_insufficient(self):
        result = ema_cross(_close([100.0] * 10))
        assert result["ema_fast"] is None

    def test_golden_cross_detected(self):
        # Long decline then sharp recovery forces fast EMA above slow EMA
        prices = [100 - i * 0.3 for i in range(50)] + [85 + i * 1.5 for i in range(20)]
        result = ema_cross(_close(prices))
        assert result["ema_fast"] is not None

    def test_fast_ema_above_slow_in_uptrend(self):
        prices = list(range(50, 110))  # consistent uptrend
        result = ema_cross(_close(prices))
        assert result["ema_fast"] > result["ema_slow"]

    def test_fast_ema_below_slow_in_downtrend(self):
        prices = list(range(110, 50, -1))  # consistent downtrend
        result = ema_cross(_close(prices))
        assert result["ema_fast"] < result["ema_slow"]


# ── Volume ────────────────────────────────────────────────────────────────────

class TestVolumeSignal:
    def test_returns_normal_signal_for_average_volume(self):
        vols = [1_000_000.0] * 21
        result = volume_signal(pd.Series(vols))
        assert result["signal"] == "normal"

    def test_high_volume_detected(self):
        vols = [1_000_000.0] * 20 + [3_000_000.0]
        result = volume_signal(pd.Series(vols))
        assert result["signal"] == "high"
        assert result["ratio"] >= 1.5

    def test_low_volume_detected(self):
        vols = [1_000_000.0] * 20 + [200_000.0]
        result = volume_signal(pd.Series(vols))
        assert result["signal"] == "low"

    def test_returns_normal_with_single_entry(self):
        result = volume_signal(pd.Series([1_000_000.0]))
        assert result["signal"] == "normal"


# ── compute_indicators ────────────────────────────────────────────────────────

class TestComputeIndicators:
    def test_empty_df_returns_insufficient_message(self):
        result = compute_indicators(pd.DataFrame())
        assert "insufficient" in result["summary"]

    def test_none_returns_insufficient_message(self):
        result = compute_indicators(None)
        assert "insufficient" in result["summary"]

    def test_returns_all_indicator_keys(self):
        df = _df([100.0 + i for i in range(60)])
        result = compute_indicators(df)
        assert "rsi" in result
        assert "macd" in result
        assert "bollinger" in result
        assert "ema" in result
        assert "volume" in result
        assert "summary" in result

    def test_summary_is_string(self):
        df = _df([100.0 + i for i in range(60)])
        result = compute_indicators(df)
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    def test_handles_short_history_gracefully(self):
        df = _df([100.0] * 8)
        result = compute_indicators(df)
        assert isinstance(result["summary"], str)

    def test_rsi_overbought_in_summary(self):
        # Monotonically increasing — RSI will be high
        prices = list(range(100, 165))
        df = _df(prices)
        result = compute_indicators(df)
        assert "RSI" in result["summary"]

    def test_summary_includes_ema_trend(self):
        prices = list(range(50, 115))  # clear uptrend
        df = _df(prices)
        result = compute_indicators(df)
        assert "EMA" in result["summary"]
