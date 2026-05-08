"""Async Polymarket Gamma API client (read-only)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx

from prediction_bot.src.api.base_client import PredictionMarketClient
from prediction_bot.src.api.models import PredictionMarket

logger = logging.getLogger(__name__)

BASE_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
_REQUEST_DELAY = 0.5

_CRYPTO_TAGS = {"crypto", "bitcoin", "ethereum", "defi", "token", "btc", "eth", "solana", "xrp"}
_POLITICS_TAGS = {"politics", "elections", "congress", "government", "president", "senate", "election"}
_SPORTS_TAGS = {
    "nfl", "nba", "mlb", "nhl", "mls", "sports", "sport", "game", "match", "team",
    "soccer", "football", "basketball", "baseball", "hockey", "tennis", "golf",
    "championship", "league", "cup", "serie", "premier", "bundesliga", "ligue",
    "ufc", "boxing", "formula", "racing", "olympics", "draft",
}
_SPORTS_QUESTION_SIGNALS = {
    " vs ", " vs. ", " o/u ", " over/under ", "fc ", " fc", "will win", "advance",
    " nfl ", " nba ", " mlb ", " nhl ", " ufc ", " mls ", "draft pick", "super bowl",
    "world cup", "champions league", " playoff", "match ", "tournament",
}


def _parse_outcome_prices(raw: str | list) -> tuple[float, float]:
    prices = json.loads(raw) if isinstance(raw, str) else raw
    return float(prices[0]), float(prices[1])


def _classify(tags: list[dict], question: str) -> str:
    q = question.lower()

    # question-level signals (most reliable)
    if any(s in q for s in _SPORTS_QUESTION_SIGNALS):
        return "sports"
    if any(k in q for k in ("bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "xrp")):
        return "crypto"

    # tag-level signals
    for t in tags:
        label = t.get("label", "").lower()
        slug = t.get("slug", "").lower()
        for key in (label, slug):
            if any(k in key for k in _CRYPTO_TAGS):
                return "crypto"
            if any(k in key for k in _SPORTS_TAGS):
                return "sports"
            if any(k in key for k in _POLITICS_TAGS):
                return "politics"

    return "politics"


def _parse_market(raw: dict) -> PredictionMarket | None:
    try:
        yes_price, no_price = _parse_outcome_prices(raw.get("outcomePrices", '["0.5","0.5"]'))
        end_date = datetime.fromisoformat(raw["endDate"].replace("Z", "+00:00"))
        tags = raw.get("tags") or []
        question = raw.get("question", "")
        category = _classify(tags, question)
        return PredictionMarket(
            id=raw["conditionId"],
            platform="polymarket",
            question=raw.get("question", ""),
            category=category,
            end_date=end_date,
            yes_price=yes_price,
            no_price=no_price,
            volume_24h=float(raw.get("volume24hr", 0) or 0),
            liquidity=float(raw.get("liquidity", 0) or 0),
            slug=raw.get("slug", ""),
            metadata={"tags": tags, "closed": raw.get("closed", False)},
        )
    except Exception as e:
        logger.debug("Failed to parse market %s: %s", raw.get("conditionId"), e)
        return None


class PolymarketClient(PredictionMarketClient):
    platform = "polymarket"

    def __init__(self):
        self._session: httpx.AsyncClient | None = None
        self._clob: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "PolymarketClient":
        self._session = httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)
        self._clob = httpx.AsyncClient(base_url=CLOB_URL, timeout=15.0)
        return self

    async def __aexit__(self, *_) -> None:
        if self._session:
            await self._session.aclose()
        if self._clob:
            await self._clob.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        await asyncio.sleep(_REQUEST_DELAY)
        for attempt in range(3):
            try:
                resp = await self._session.get(path, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await asyncio.sleep(5 * (2 ** attempt))
                else:
                    raise
        return {}

    async def get_active_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        order: str = "volume_24hr",
        tag_id: int | None = None,
    ) -> list[PredictionMarket]:
        params: dict = {"active": "true", "closed": "false", "limit": limit, "offset": offset, "order": order}
        if tag_id:
            params["tag_id"] = tag_id
        data = await self._get("/markets", params)
        if isinstance(data, list):
            markets = data
        else:
            markets = data.get("markets", [])
        return [m for raw in markets if (m := _parse_market(raw))]

    async def get_market_status(self, condition_id: str) -> dict:
        await asyncio.sleep(_REQUEST_DELAY)
        try:
            resp = await self._clob.get(f"/markets/{condition_id}")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.debug("CLOB market lookup failed for %s: %s", condition_id, e)
            return {"resolved": False, "winner": None}

        if not data.get("closed", False):
            return {"resolved": False, "winner": None}

        tokens = {t["outcome"]: t["price"] for t in data.get("tokens", [])}
        yes_price = float(tokens.get("Yes", 0.5))
        no_price = float(tokens.get("No", 0.5))
        if yes_price > 0.9:
            winner = "YES"
        elif no_price > 0.9:
            winner = "NO"
        else:
            winner = None  # cancelled / not yet settled
        return {"resolved": True, "winner": winner}

    async def get_near_expiry_markets(
        self,
        hours: int = 48,
        min_liquidity: float = 1000.0,
        limit: int = 500,
    ) -> list[PredictionMarket]:
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=hours)
        params: dict = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "end_date_asc",
        }
        data = await self._get("/markets", params)
        markets_raw = data if isinstance(data, list) else data.get("markets", [])
        markets = [m for raw in markets_raw if (m := _parse_market(raw))]
        return [
            m for m in markets
            if m.liquidity >= min_liquidity and now <= m.end_date <= cutoff
        ]
