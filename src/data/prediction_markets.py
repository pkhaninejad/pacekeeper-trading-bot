"""
Prediction market probabilities from Polymarket (macro) and Kalshi (ticker-specific).

Fetchers fail silently — log warnings and return [] so a missing API key or
network error never breaks the trading cycle.
"""

from __future__ import annotations

import json
import logging
import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime

import requests
import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = pathlib.Path(__file__).parent / "prediction_markets_config.yaml"

_cache: dict[str, dict] = {}  # {"macro" | ticker: {"data": list[MarketProb], "fetched_at": datetime}}


@dataclass
class MarketProb:
    source: str         # "polymarket" | "kalshi"
    event: str          # human-readable label
    ticker: str | None  # None for macro events
    yes_prob: float     # 0.0–1.0
    volume_usd: int     # liquidity indicator
    url: str            # traceability; not injected into prompt
    fetched_at: datetime


def _load_config() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text())


def _is_fresh(entry: dict, ttl: int) -> bool:
    age = (datetime.now(UTC) - entry["fetched_at"]).total_seconds()
    return age < ttl


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------

_POLYMARKET_BASE = "https://gamma-api.polymarket.com"


def _fetch_polymarket_macro(macro_entries: list[dict]) -> list[MarketProb]:
    """Fetch YES probabilities for macro events from Polymarket public API."""
    results: list[MarketProb] = []
    for entry in macro_entries:
        slug = entry.get("polymarket_slug")
        if not slug:
            continue
        try:
            url = f"{_POLYMARKET_BASE}/events?slug={slug}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            markets = data.get("markets", [])
            if not markets:
                logger.warning("Polymarket: no markets found for slug '%s'", slug)
                continue
            m = markets[0]
            prices_raw = m.get("outcomePrices", '["0.5", "0.5"]')
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            yes_prob = float(prices[0])
            volume_usd = int(float(m.get("volume", 0)))
            market_url = f"https://polymarket.com/event/{slug}"
            results.append(MarketProb(
                source="polymarket",
                event=entry["label"],
                ticker=None,
                yes_prob=yes_prob,
                volume_usd=volume_usd,
                url=market_url,
                fetched_at=datetime.now(UTC),
            ))
        except Exception as e:
            logger.warning("Polymarket fetch failed for slug '%s': %s", slug, e)
    return results


# ---------------------------------------------------------------------------
# Kalshi
# ---------------------------------------------------------------------------

_KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"


def _fetch_kalshi_ticker(ticker: str, entries: list[dict], api_key: str) -> list[MarketProb]:
    """Fetch YES probabilities for a ticker's events from Kalshi."""
    if not api_key:
        logger.info("KALSHI_API_KEY not set — skipping Kalshi for %s", ticker)
        return []

    headers = {"Authorization": f"Bearer {api_key}"}
    results: list[MarketProb] = []

    for entry in entries:
        series = entry.get("kalshi_series")
        keywords = entry.get("discovery_keywords", [])
        label = entry["label"]

        markets: list[dict] = []

        if series:
            try:
                resp = requests.get(
                    f"{_KALSHI_BASE}/markets",
                    params={"series_ticker": series},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                markets = resp.json().get("markets", [])
            except Exception as e:
                logger.warning("Kalshi series fetch failed for '%s': %s", series, e)

        if not markets and keywords:
            query = " ".join(keywords[:2])
            try:
                resp = requests.get(
                    f"{_KALSHI_BASE}/markets",
                    params={"search": query, "status": "open", "limit": 5},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
                markets = resp.json().get("markets", [])
            except Exception as e:
                logger.warning("Kalshi discovery failed for ticker '%s' query '%s': %s", ticker, query, e)

        if not markets:
            continue

        m = markets[0]
        yes_prob = float(m.get("yes_ask", m.get("yes_bid", 0.5)))
        volume_usd = int(m.get("volume", 0))
        market_ticker = m.get("ticker", "")
        market_url = f"https://kalshi.com/markets/{market_ticker}"

        results.append(MarketProb(
            source="kalshi",
            event=label,
            ticker=ticker,
            yes_prob=yes_prob,
            volume_usd=volume_usd,
            url=market_url,
            fetched_at=datetime.now(UTC),
        ))

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

from src.config.settings import settings as _settings


def get_prediction_market_context(watchlist: list[str]) -> dict[str, list[MarketProb]]:
    """
    Fetch and cache prediction market probabilities for macro events and each
    watchlist ticker. Returns {"macro": [...], "NVDA": [...], ...}.
    Both fetchers fail silently — missing keys or network errors return [].
    """
    ttl = _settings.PREDICTION_MARKETS_CACHE_TTL
    config = _load_config()

    result: dict[str, list[MarketProb]] = {}

    # --- macro ---
    cache_key = "__macro__"
    if cache_key in _cache and _is_fresh(_cache[cache_key], ttl):
        result["macro"] = _cache[cache_key]["data"]
    else:
        macro_probs = _fetch_polymarket_macro(config.get("macro", []))
        _cache[cache_key] = {"data": macro_probs, "fetched_at": datetime.now(UTC)}
        result["macro"] = macro_probs

    # --- per ticker ---
    ticker_configs: dict[str, list[dict]] = config.get("tickers", {})
    for ticker in watchlist:
        if ticker in _cache and _is_fresh(_cache[ticker], ttl):
            result[ticker] = _cache[ticker]["data"]
            continue
        entries = ticker_configs.get(ticker, [])
        if not entries:
            result[ticker] = []
            continue
        probs = _fetch_kalshi_ticker(ticker, entries, _settings.KALSHI_API_KEY)
        _cache[ticker] = {"data": probs, "fetched_at": datetime.now(UTC)}
        result[ticker] = probs

    return result
