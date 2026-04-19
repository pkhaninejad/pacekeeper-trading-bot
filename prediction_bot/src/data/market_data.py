"""External data enrichment for market candidates."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"

_CRYPTO_SYMBOLS = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "bnb": "binancecoin",
}


async def get_crypto_price(symbol: str) -> dict | None:
    """Fetch current price from CoinGecko free API. Returns None on error."""
    coin_id = _CRYPTO_SYMBOLS.get(symbol.lower(), symbol.lower())
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_COINGECKO_BASE}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
            )
            resp.raise_for_status()
            data = resp.json()
            price = data.get(coin_id, {}).get("usd")
            if price:
                return {"symbol": symbol.upper(), "price_usd": price, "coin_id": coin_id}
    except Exception as e:
        logger.debug("CoinGecko fetch failed for %s: %s", symbol, e)
    return None


async def get_crypto_context(question: str) -> str:
    """Extract crypto context for a market question."""
    question_lower = question.lower()
    for sym in _CRYPTO_SYMBOLS:
        if sym in question_lower:
            price_data = await get_crypto_price(sym)
            if price_data:
                return f"Current {price_data['symbol']} price: ${price_data['price_usd']:,.2f} USD"
    return ""


async def get_sports_scores(query: str) -> str:
    """Fetch live/recent NBA scores via ESPN public API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            )
            resp.raise_for_status()
            data = resp.json()
            games = data.get("events", [])[:3]
            if not games:
                return ""
            lines = []
            for g in games:
                name = g.get("name", "")
                status = g.get("status", {}).get("type", {}).get("description", "")
                lines.append(f"{name} ({status})")
            return "Recent NBA games: " + "; ".join(lines)
    except Exception as e:
        logger.debug("ESPN fetch failed: %s", e)
    return ""


async def get_news_headlines(query: str, max_results: int = 3) -> str:
    return ""
