"""
Market regime detection using SPY 200-day EMA and VIX.

Classifies current market conditions into BULL / NEUTRAL / BEAR / EXTREME_FEAR
and returns a position_size_multiplier the risk manager applies to max position size.

Results are cached for REGIME_CACHE_TTL seconds (1 hour) — no need to recalculate
every 5-minute cycle.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from src.api.models import RegimeResult

logger = logging.getLogger(__name__)

REGIME_CACHE_TTL = 3600  # 1 hour

_CACHE: dict = {}
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="regime")


def _fetch_spy() -> "pd.DataFrame":
    import yfinance as yf
    t = yf.Ticker("SPY")
    return t.history(period="1y", auto_adjust=True)


def _fetch_vix() -> "pd.DataFrame":
    import yfinance as yf
    t = yf.Ticker("^VIX")
    return t.history(period="5d", auto_adjust=True)


def _classify(spy_vs_200ema: float, vix: float) -> RegimeResult:
    """Pure classification logic — no I/O. Testable in isolation."""
    if vix > 40:
        return RegimeResult(
            regime="EXTREME_FEAR",
            spy_vs_200ema=spy_vs_200ema,
            vix=vix,
            position_size_multiplier=0.0,
            description=f"VIX={vix:.1f} — extreme fear, all new positions blocked",
        )
    if spy_vs_200ema > 2.0 and vix < 20:
        return RegimeResult(
            regime="BULL",
            spy_vs_200ema=spy_vs_200ema,
            vix=vix,
            position_size_multiplier=1.0,
            description=f"SPY {spy_vs_200ema:+.1f}% above 200EMA, VIX={vix:.1f} — bull market",
        )
    if spy_vs_200ema < -2.0 and vix > 30:
        return RegimeResult(
            regime="BEAR",
            spy_vs_200ema=spy_vs_200ema,
            vix=vix,
            position_size_multiplier=0.50,
            description=f"SPY {spy_vs_200ema:+.1f}% below 200EMA, VIX={vix:.1f} — bear market",
        )
    return RegimeResult(
        regime="NEUTRAL",
        spy_vs_200ema=spy_vs_200ema,
        vix=vix,
        position_size_multiplier=0.75,
        description=f"SPY {spy_vs_200ema:+.1f}% vs 200EMA, VIX={vix:.1f} — neutral",
    )


def _neutral_fallback() -> RegimeResult:
    return RegimeResult(
        regime="NEUTRAL",
        spy_vs_200ema=0.0,
        vix=0.0,
        position_size_multiplier=1.0,
        description="Regime data unavailable — defaulting to NEUTRAL (full sizing)",
    )


def _is_fresh() -> bool:
    if "fetched_at" not in _CACHE:
        return False
    return (datetime.now(timezone.utc) - _CACHE["fetched_at"]).total_seconds() < REGIME_CACHE_TTL


def get_regime() -> RegimeResult:
    """
    Return current market regime. Cached for 1 hour.
    Falls back to NEUTRAL (multiplier 1.0) on any yfinance failure.
    """
    if _is_fresh():
        return _CACHE["result"]

    try:
        import yfinance  # noqa — check availability before spinning threads
    except ImportError:
        logger.warning("yfinance not installed — regime detection disabled, using NEUTRAL")
        return _neutral_fallback()

    try:
        futures = {
            _executor.submit(_fetch_spy): "spy",
            _executor.submit(_fetch_vix): "vix",
        }
        data = {}
        for future in as_completed(futures, timeout=15):
            key = futures[future]
            data[key] = future.result()

        spy_hist = data.get("spy")
        vix_hist = data.get("vix")

        if spy_hist is None or spy_hist.empty or len(spy_hist) < 200:
            logger.warning("Regime: insufficient SPY history — using NEUTRAL")
            return _neutral_fallback()
        if vix_hist is None or vix_hist.empty:
            logger.warning("Regime: VIX data unavailable — using NEUTRAL")
            return _neutral_fallback()

        spy_close = spy_hist["Close"].dropna()
        ema200 = spy_close.ewm(span=200, adjust=False).mean().iloc[-1]
        spy_current = spy_close.iloc[-1]
        spy_vs_200ema = (spy_current - ema200) / ema200 * 100

        vix = float(vix_hist["Close"].dropna().iloc[-1])

        result = _classify(spy_vs_200ema=round(spy_vs_200ema, 2), vix=round(vix, 2))
        _CACHE["result"] = result
        _CACHE["fetched_at"] = datetime.now(timezone.utc)
        logger.info("Market regime: %s (SPY %+.1f%% vs 200EMA, VIX=%.1f)", result.regime, spy_vs_200ema, vix)
        return result

    except Exception as e:
        logger.warning("Regime detection failed: %s — using NEUTRAL", e)
        return _neutral_fallback()
