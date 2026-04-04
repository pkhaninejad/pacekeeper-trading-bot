"""
Real-time price feed using yfinance.

Fetches 30-day OHLCV history and latest price for each watchlist ticker.
Results are cached for CACHE_TTL seconds to avoid hammering Yahoo Finance.

Uses yf.Ticker().history() (not yf.download()) — more reliable inside
asyncio/FastAPI contexts because it avoids yfinance's internal threading.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # seconds — refresh at most every 5 minutes

_cache: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pricefeed")


def _is_fresh(entry: dict) -> bool:
    return (datetime.utcnow() - entry["fetched_at"]).total_seconds() < CACHE_TTL


def _fetch_one(ticker: str) -> Optional[dict]:
    """Fetch price data for a single ticker. Run in a thread executor."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo", auto_adjust=True)
        if hist.empty:
            logger.warning("Price feed: empty history for %s", ticker)
            return None

        closes = hist["Close"].dropna().tolist()
        if not closes:
            return None

        current = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else current
        change_pct = ((current - prev) / prev * 100) if prev else 0.0

        sma_10 = sum(closes[-10:]) / min(10, len(closes))
        sma_30 = sum(closes) / len(closes)
        rsi = _rsi(closes, 14)

        volumes = hist["Volume"].dropna().tolist()
        avg_vol = sum(volumes) / len(volumes) if volumes else 0

        return {
            "current_price": round(current, 4),
            "change_pct_1d": round(change_pct, 2),
            "high_30d": round(max(closes), 4),
            "low_30d": round(min(closes), 4),
            "avg_volume_30d": int(avg_vol),
            "sma_10": round(sma_10, 4),
            "sma_30": round(sma_30, 4),
            "rsi_14": round(rsi, 1) if rsi is not None else None,
            "history": [round(c, 4) for c in closes[-10:]],
        }
    except Exception as e:
        logger.warning("Price feed failed for %s: %s", ticker, e)
        return None


def get_price_summary(tickers: list[str]) -> dict[str, dict]:
    """
    Return a dict keyed by ticker with keys:
      current_price, change_pct_1d, high_30d, low_30d, avg_volume_30d,
      sma_10, sma_30, rsi_14, history (last 10 closes)
    Falls back gracefully if yfinance is unavailable or a ticker fails.
    """
    try:
        import yfinance  # noqa — check availability before spinning threads
    except ImportError:
        logger.warning("yfinance not installed — price feed disabled")
        return {}

    result: dict[str, dict] = {}
    stale = [t for t in tickers if t not in _cache or not _is_fresh(_cache[t])]

    # Serve cached entries immediately
    for ticker in tickers:
        if ticker not in stale:
            result[ticker] = _cache[ticker]["data"]

    if not stale:
        return result

    # Fetch stale tickers in parallel threads (keeps asyncio loop unblocked)
    futures = {_executor.submit(_fetch_one, t): t for t in stale}
    for future in as_completed(futures, timeout=15):
        ticker = futures[future]
        try:
            data = future.result()
            if data:
                _cache[ticker] = {"data": data, "fetched_at": datetime.utcnow()}
                result[ticker] = data
                logger.info("Price feed OK: %s @ %.2f (RSI %.1f)",
                            ticker, data["current_price"], data["rsi_14"] or 0)
        except Exception as e:
            logger.warning("Price feed thread error for %s: %s", ticker, e)

    return result


def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
