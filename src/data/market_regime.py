"""
Market regime detection — classifies current market as BULL/NEUTRAL/BEAR/EXTREME_FEAR.

Uses SPY (trend) and ^VIX (fear gauge) via yfinance. Results are cached for 5 minutes.
Fails silently: returns NEUTRAL if yfinance is unavailable or the fetch fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]

_CACHE_TTL = 300  # seconds — 5 minutes, same as price_feed.py
_cache: dict = {}  # {"regime": MarketRegime, "fetched_at": datetime}


@dataclass
class MarketRegime:
    label: str            # "BULL" | "NEUTRAL" | "BEAR" | "EXTREME_FEAR"
    vix: float            # latest VIX close
    spy_change_pct: float # SPY 1-day % change
    risk_multiplier: float  # 1.0 / 0.8 / 0.5 / 0.0


_NEUTRAL_FALLBACK = MarketRegime(
    label="NEUTRAL", vix=0.0, spy_change_pct=0.0, risk_multiplier=0.8
)


def _cache_fresh() -> bool:
    if not _cache:
        return False
    age = (datetime.utcnow() - _cache["fetched_at"]).total_seconds()
    return age < _CACHE_TTL


def _classify(vix: float, spy_above_sma10: bool, spy_above_sma30: bool) -> tuple[str, float]:
    """Return (label, risk_multiplier) based on VIX level and SPY vs SMAs."""
    if vix > 30:
        return "EXTREME_FEAR", 0.0
    if vix > 25 or (not spy_above_sma10 and not spy_above_sma30):
        return "BEAR", 0.5
    if vix > 20 or not spy_above_sma10 or not spy_above_sma30:
        return "NEUTRAL", 0.8
    return "BULL", 1.0


class RegimeDetector:
    """Fetches SPY + VIX from yfinance and classifies the market regime."""

    def get_regime(self, use_cache: bool = True) -> MarketRegime:
        """Return the current MarketRegime. Uses cache if fresh and use_cache=True."""
        if use_cache and _cache_fresh():
            return _cache["regime"]

        regime = self._fetch()
        _cache["regime"] = regime
        _cache["fetched_at"] = datetime.utcnow()
        return regime

    def _fetch(self) -> MarketRegime:
        if yf is None:
            logger.warning("yfinance not available — regime defaulting to NEUTRAL")
            return _NEUTRAL_FALLBACK

        try:
            spy_hist = yf.Ticker("SPY").history(period="3mo", auto_adjust=True)
            vix_hist = yf.Ticker("^VIX").history(period="5d", auto_adjust=True)

            if spy_hist.empty or vix_hist.empty:
                logger.warning("Regime fetch: empty history — defaulting to NEUTRAL")
                return _NEUTRAL_FALLBACK

            spy_closes = spy_hist["Close"].dropna().tolist()
            vix_closes = vix_hist["Close"].dropna().tolist()

            if len(spy_closes) < 30 or not vix_closes:
                logger.warning("Regime fetch: insufficient history — defaulting to NEUTRAL")
                return _NEUTRAL_FALLBACK

            current_spy = spy_closes[-1]
            prev_spy = spy_closes[-2]
            spy_change_pct = ((current_spy - prev_spy) / prev_spy * 100) if prev_spy else 0.0

            sma10 = sum(spy_closes[-10:]) / 10
            sma30 = sum(spy_closes[-30:]) / 30
            spy_above_sma10 = current_spy >= sma10
            spy_above_sma30 = current_spy >= sma30

            vix = vix_closes[-1]
            label, risk_multiplier = _classify(vix, spy_above_sma10, spy_above_sma30)

            regime = MarketRegime(
                label=label,
                vix=round(vix, 2),
                spy_change_pct=round(spy_change_pct, 2),
                risk_multiplier=risk_multiplier,
            )
            logger.info(
                "Market regime: %s (VIX=%.1f, SPY 1d=%+.1f%%, above SMA10=%s, SMA30=%s)",
                label, vix, spy_change_pct, spy_above_sma10, spy_above_sma30,
            )
            return regime

        except Exception as e:
            logger.warning("Regime detection failed: %s — defaulting to NEUTRAL", e)
            return _NEUTRAL_FALLBACK
