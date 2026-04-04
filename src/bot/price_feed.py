"""
Real-time price feed using yfinance.

Fetches 30-day OHLCV history and latest price for each watchlist ticker.
Results are cached for CACHE_TTL seconds to avoid hammering Yahoo Finance.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # seconds — refresh at most every 5 minutes

_cache: dict[str, dict] = {}


def _is_fresh(entry: dict) -> bool:
    return (datetime.utcnow() - entry["fetched_at"]).total_seconds() < CACHE_TTL


def get_price_summary(tickers: list[str]) -> dict[str, dict]:
    """
    Return a dict keyed by ticker with keys:
      current_price, change_pct_1d, high_30d, low_30d, avg_volume_30d,
      sma_10, sma_30, rsi_14 (approximate), history (list of close prices)
    Falls back gracefully if yfinance is unavailable or a ticker fails.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — price feed disabled")
        return {}

    result: dict[str, dict] = {}
    for ticker in tickers:
        # Return cached data if still fresh
        if ticker in _cache and _is_fresh(_cache[ticker]):
            result[ticker] = _cache[ticker]["data"]
            continue

        try:
            hist = yf.download(
                ticker,
                period="1mo",
                interval="1d",
                progress=False,
                auto_adjust=True,
            )
            if hist.empty:
                continue

            close_col = hist["Close"]
            # yfinance >=0.2 may return a DataFrame with ticker as column
            if hasattr(close_col, "squeeze"):
                close_col = close_col.squeeze()
            closes = close_col.dropna().tolist()
            if not closes:
                continue

            current = closes[-1]
            prev = closes[-2] if len(closes) >= 2 else current
            change_pct = ((current - prev) / prev * 100) if prev else 0.0

            sma_10 = sum(closes[-10:]) / min(10, len(closes))
            sma_30 = sum(closes) / len(closes)

            # Approximate RSI-14
            rsi = _rsi(closes, 14)

            vol_col = hist["Volume"]
            if hasattr(vol_col, "squeeze"):
                vol_col = vol_col.squeeze()
            volumes = vol_col.dropna().tolist()
            avg_vol = sum(volumes) / len(volumes) if volumes else 0

            data = {
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
            _cache[ticker] = {"data": data, "fetched_at": datetime.utcnow()}
            result[ticker] = data
        except Exception as e:
            logger.warning("Price feed failed for %s: %s", ticker, e)

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
