"""
Technical indicators computed from OHLCV DataFrames.

All indicators are implemented with pure pandas/numpy — no external TA library.
Each function accepts a DataFrame with columns: Open, High, Low, Close, Volume.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── individual indicators ─────────────────────────────────────────────────────

def rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """Relative Strength Index. Returns latest value or None if insufficient data."""
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean().iloc[-1]
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
         ) -> dict[str, Optional[float]]:
    """
    MACD line, signal line, and histogram.
    Returns dict with keys: macd, signal, histogram, crossover
    crossover: 'bullish' | 'bearish' | None
    """
    if len(close) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None, "crossover": None}

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    crossover = None
    if len(macd_line) >= 2:
        prev_above = macd_line.iloc[-2] > signal_line.iloc[-2]
        curr_above = macd_line.iloc[-1] > signal_line.iloc[-1]
        if not prev_above and curr_above:
            crossover = "bullish"
        elif prev_above and not curr_above:
            crossover = "bearish"

    return {
        "macd": round(macd_line.iloc[-1], 4),
        "signal": round(signal_line.iloc[-1], 4),
        "histogram": round(histogram.iloc[-1], 4),
        "crossover": crossover,
    }


def bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0
                    ) -> dict[str, Optional[float]]:
    """
    Bollinger Bands. Returns upper, middle, lower, %B, and band_signal.
    band_signal: 'upper' (overbought) | 'lower' (oversold) | 'middle' | None
    """
    if len(close) < period:
        return {"upper": None, "middle": None, "lower": None, "pct_b": None, "band_signal": None}

    rolling = close.rolling(period)
    middle = rolling.mean().iloc[-1]
    std = rolling.std().iloc[-1]
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    current = close.iloc[-1]
    band_width = upper - lower
    pct_b = ((current - lower) / band_width) if band_width > 0 else 0.5

    if pct_b >= 0.95:
        band_signal = "upper"
    elif pct_b <= 0.05:
        band_signal = "lower"
    else:
        band_signal = "middle"

    return {
        "upper": round(upper, 4),
        "middle": round(middle, 4),
        "lower": round(lower, 4),
        "pct_b": round(pct_b, 3),
        "band_signal": band_signal,
    }


def ema_cross(close: pd.Series, fast: int = 20, slow: int = 50
              ) -> dict[str, Optional[float]]:
    """
    EMA fast/slow values and golden/death cross detection.
    cross: 'golden' | 'death' | None
    """
    if len(close) < slow:
        return {"ema_fast": None, "ema_slow": None, "cross": None}

    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()

    cross = None
    if len(ema_f) >= 2:
        prev_above = ema_f.iloc[-2] > ema_s.iloc[-2]
        curr_above = ema_f.iloc[-1] > ema_s.iloc[-1]
        if not prev_above and curr_above:
            cross = "golden"
        elif prev_above and not curr_above:
            cross = "death"

    return {
        "ema_fast": round(ema_f.iloc[-1], 4),
        "ema_slow": round(ema_s.iloc[-1], 4),
        "cross": cross,
    }


def volume_signal(volume: pd.Series) -> dict[str, Optional[float]]:
    """
    Compares latest volume to 20-day average.
    signal: 'high' (>150% avg) | 'low' (<50% avg) | 'normal'
    """
    if len(volume) < 2:
        return {"latest": None, "avg_20": None, "ratio": None, "signal": "normal"}

    avg = volume.rolling(min(20, len(volume))).mean().iloc[-1]
    latest = volume.iloc[-1]
    ratio = (latest / avg) if avg > 0 else 1.0

    if ratio >= 1.5:
        signal = "high"
    elif ratio <= 0.5:
        signal = "low"
    else:
        signal = "normal"

    return {
        "latest": int(latest),
        "avg_20": int(avg),
        "ratio": round(ratio, 2),
        "signal": signal,
    }


# ── main entry point ──────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> dict:
    """
    Compute all technical indicators from an OHLCV DataFrame.

    Args:
        df: DataFrame with columns Open, High, Low, Close, Volume
            (as returned by yf.Ticker().history())

    Returns:
        dict with keys: rsi, macd, bollinger, ema, volume, summary
        `summary` is a plain-English string ready for the Claude prompt.
    """
    if df is None or df.empty or len(df) < 5:
        return {"summary": "(insufficient price history for indicators)"}

    close = df["Close"].dropna()
    volume = df["Volume"].dropna() if "Volume" in df.columns else pd.Series([], dtype=float)

    result = {
        "rsi": rsi(close),
        "macd": macd(close),
        "bollinger": bollinger_bands(close),
        "ema": ema_cross(close),
        "volume": volume_signal(volume),
    }
    result["summary"] = _build_summary(result)
    return result


def _build_summary(ind: dict) -> str:
    """Produce a plain-English one-liner for the Claude prompt."""
    parts = []

    # RSI
    rsi_val = ind.get("rsi")
    if rsi_val is not None:
        if rsi_val >= 70:
            parts.append(f"RSI={rsi_val} (overbought)")
        elif rsi_val <= 30:
            parts.append(f"RSI={rsi_val} (oversold)")
        else:
            parts.append(f"RSI={rsi_val} (neutral)")

    # MACD
    m = ind.get("macd", {})
    if m.get("crossover"):
        parts.append(f"MACD={m['crossover']} crossover")
    elif m.get("histogram") is not None:
        direction = "bullish" if m["histogram"] > 0 else "bearish"
        parts.append(f"MACD={direction} (hist={m['histogram']})")

    # Bollinger Bands
    bb = ind.get("bollinger", {})
    if bb.get("band_signal") == "upper":
        parts.append(f"price at upper BB (pct_b={bb.get('pct_b')}, overbought)")
    elif bb.get("band_signal") == "lower":
        parts.append(f"price at lower BB (pct_b={bb.get('pct_b')}, oversold)")

    # EMA cross
    e = ind.get("ema", {})
    if e.get("cross") == "golden":
        parts.append("EMA20 golden cross above EMA50")
    elif e.get("cross") == "death":
        parts.append("EMA20 death cross below EMA50")
    elif e.get("ema_fast") and e.get("ema_slow"):
        trend = "above" if e["ema_fast"] > e["ema_slow"] else "below"
        parts.append(f"EMA20 {trend} EMA50")

    # Volume
    v = ind.get("volume", {})
    if v.get("signal") == "high":
        parts.append(f"high volume ({v.get('ratio')}x avg)")
    elif v.get("signal") == "low":
        parts.append(f"low volume ({v.get('ratio')}x avg)")

    return ", ".join(parts) if parts else "(no strong signal)"
