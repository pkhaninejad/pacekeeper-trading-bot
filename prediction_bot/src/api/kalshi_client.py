"""Async Kalshi Exchange API v2 client."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

from prediction_bot.src.api.base_client import PredictionMarketClient
from prediction_bot.src.api.models import PredictionMarket
from prediction_bot.src.config.settings import PredictionBotSettings, pm_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
_REQUEST_DELAY = 0.2

_SERIES_CATEGORY: dict[str, str] = {
    "CRYPTO": "crypto", "BITCOIN": "crypto", "ETHEREUM": "crypto",
    "NFL": "sports", "NBA": "sports", "MLB": "sports", "NHL": "sports", "SOCCER": "sports",
    "ELECTIONS": "politics", "CONGRESS": "politics", "PRESIDENT": "politics",
    "SCOTUS": "politics", "GOVERNMENT": "politics",
}


def _parse_kalshi_market(raw: dict) -> PredictionMarket | None:
    try:
        close_time = datetime.fromisoformat(raw["close_time"].replace("Z", "+00:00"))
        yes_price = ((raw.get("yes_bid", 50) + raw.get("yes_ask", 50)) / 2) / 100
        no_price = ((raw.get("no_bid", 50) + raw.get("no_ask", 50)) / 2) / 100
        series = raw.get("series_ticker", "").upper()
        category = "politics"
        for prefix, cat in _SERIES_CATEGORY.items():
            if series.startswith(prefix):
                category = cat
                break
        return PredictionMarket(
            id=raw["ticker"],
            platform="kalshi",
            question=raw.get("title", raw.get("ticker", "")),
            category=category,
            end_date=close_time,
            yes_price=yes_price,
            no_price=no_price,
            volume_24h=float(raw.get("volume", 0) or 0),
            liquidity=float(raw.get("volume", 0) or 0),
            slug=raw.get("ticker", ""),
            metadata={"series_ticker": raw.get("series_ticker"), "status": raw.get("status")},
        )
    except Exception as e:
        logger.debug("Failed to parse Kalshi market %s: %s", raw.get("ticker"), e)
        return None


class KalshiClient(PredictionMarketClient):
    platform = "kalshi"

    def __init__(self, settings: PredictionBotSettings = pm_settings):
        self._settings = settings
        self._session: httpx.AsyncClient | None = None
        self._token: str | None = None

    async def __aenter__(self) -> "KalshiClient":
        self._session = httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)
        return self

    async def __aexit__(self, *_) -> None:
        if self._session:
            await self._session.aclose()

    async def _login(self):
        if not self._settings.KALSHI_API_KEY:
            return
        try:
            resp = await self._session.post(
                "/log-in",
                json={"email": self._settings.KALSHI_API_KEY, "password": self._settings.KALSHI_API_SECRET},
            )
            resp.raise_for_status()
            self._token = resp.json().get("token")
        except Exception as e:
            logger.warning("Kalshi login failed: %s", e)

    def _headers(self) -> dict:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        await asyncio.sleep(_REQUEST_DELAY)
        for attempt in range(3):
            try:
                resp = await self._session.get(path, params=params, headers=self._headers())
                if resp.status_code == 401:
                    await self._login()
                    continue
                if resp.status_code == 429:
                    await asyncio.sleep(5 * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning("Kalshi HTTP error %s for %s: %s", e.response.status_code, path, e)
                return {}
        return {}

    async def _get_markets_raw(
        self, cursor: str | None = None, limit: int = 200
    ) -> tuple[list[dict], str | None]:
        params: dict = {"status": "open", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        data = await self._get("/markets", params)
        return data.get("markets", []), data.get("cursor")

    async def get_market_status(self, ticker: str) -> dict:
        data = await self._get(f"/markets/{ticker}")
        status = data.get("status", "open")
        result = data.get("result")
        if status in ("settled", "finalized") and result:
            return {"resolved": True, "winner": result.upper()}
        return {"resolved": False, "winner": None}

    async def get_near_expiry_markets(
        self,
        hours: int = 48,
        min_liquidity: float = 1000.0,
        limit: int = 200,
    ) -> list[PredictionMarket]:
        if not self._settings.KALSHI_ENABLED:
            return []
        if not self._token:
            await self._login()
        raw_markets, _ = await self._get_markets_raw(limit=limit)
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=hours)
        return [
            m for raw in raw_markets
            if (m := _parse_kalshi_market(raw))
            and now < m.end_date <= cutoff
            and m.liquidity >= min_liquidity
        ]
