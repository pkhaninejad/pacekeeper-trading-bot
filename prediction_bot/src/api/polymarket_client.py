"""Async Polymarket Gamma API client (read-only)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx

from prediction_bot.src.api.models import PredictionMarket

logger = logging.getLogger(__name__)

BASE_URL = "https://gamma-api.polymarket.com"
_REQUEST_DELAY = 0.5

_CRYPTO_TAGS = {"crypto", "bitcoin", "ethereum", "defi", "token"}
_POLITICS_TAGS = {"politics", "elections", "congress", "government", "president"}


def _parse_outcome_prices(raw: str | list) -> tuple[float, float]:
    prices = json.loads(raw) if isinstance(raw, str) else raw
    return float(prices[0]), float(prices[1])


def _classify_tags(tags: list[dict]) -> str:
    for t in tags:
        label = t.get("label", "").lower()
        slug = t.get("slug", "").lower()
        for key in (label, slug):
            if any(k in key for k in _CRYPTO_TAGS):
                return "crypto"
            if any(k in key for k in _POLITICS_TAGS):
                return "politics"
    for t in tags:
        label = t.get("label", "").lower()
        if any(k in label for k in ("nfl", "nba", "mlb", "sport", "game", "match", "team")):
            return "sports"
    return "politics"


def _parse_market(raw: dict) -> PredictionMarket | None:
    try:
        yes_price, no_price = _parse_outcome_prices(raw.get("outcomePrices", '["0.5","0.5"]'))
        end_date = datetime.fromisoformat(raw["endDate"].replace("Z", "+00:00"))
        tags = raw.get("tags") or []
        category = _classify_tags(tags)
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


class PolymarketClient:
    def __init__(self):
        self._session: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._session = httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)
        return self

    async def __aexit__(self, *_):
        if self._session:
            await self._session.aclose()

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
        raw = await self._get(f"/markets/{condition_id}")
        data = raw[0] if isinstance(raw, list) and raw else (raw if isinstance(raw, dict) else {})
        closed = data.get("closed", False)
        if not closed:
            return {"resolved": False, "winner": None}
        yes_price, no_price = _parse_outcome_prices(data.get("outcomePrices", '["0.5","0.5"]'))
        winner = "YES" if yes_price > 0.9 else ("NO" if no_price > 0.9 else None)
        return {"resolved": closed, "winner": winner}

    async def get_near_expiry_markets(
        self,
        hours: int = 48,
        min_liquidity: float = 1000.0,
        limit: int = 200,
    ) -> list[PredictionMarket]:
        markets = await self.get_active_markets(limit=limit)
        cutoff = datetime.now(UTC) + timedelta(hours=hours)
        return [
            m for m in markets
            if m.end_date <= cutoff
            and m.end_date > datetime.now(UTC)
            and m.liquidity >= min_liquidity
        ]
