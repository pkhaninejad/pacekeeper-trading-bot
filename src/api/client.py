"""
Trading212 REST API client.

Docs: https://docs.trading212.com/api
Base URL (demo): https://demo.trading212.com/api/v0
Base URL (live): https://live.trading212.com/api/v0

Auth: HTTP Basic  → Base64("API_KEY:API_SECRET")
"""

import base64
import asyncio
import logging
from typing import Any, Optional
import httpx
from src.config.settings import settings
from src.api.models import (
    AccountInfo, CashInfo, Position, Order,
    Instrument, MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
)

logger = logging.getLogger(__name__)

_RATE_LIMIT_DELAY = 0.5   # seconds between requests


def _auth_header() -> str:
    raw = f"{settings.T212_API_KEY}:{settings.T212_API_SECRET}"
    encoded = base64.b64encode(raw.encode()).decode()
    return f"Basic {encoded}"


class Trading212Client:
    def __init__(self):
        self._base = settings.t212_base_url
        self._headers = {
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers=self._headers,
            timeout=30,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict = None) -> Any:
        async with self._lock:
            await asyncio.sleep(_RATE_LIMIT_DELAY)
            r = await self._client.get(path, params=params)
            r.raise_for_status()
            logger.debug("GET %s → %s", path, r.status_code)
            return r.json()

    async def _post(self, path: str, body: dict) -> Any:
        async with self._lock:
            await asyncio.sleep(_RATE_LIMIT_DELAY)
            r = await self._client.post(path, json=body)
            r.raise_for_status()
            logger.debug("POST %s → %s", path, r.status_code)
            return r.json()

    async def _delete(self, path: str) -> Any:
        async with self._lock:
            await asyncio.sleep(_RATE_LIMIT_DELAY)
            r = await self._client.delete(path)
            r.raise_for_status()
            logger.debug("DELETE %s → %s", path, r.status_code)
            return r.json() if r.content else {}

    # -------------------------------------------------------------------------
    # Account
    # -------------------------------------------------------------------------

    async def get_account_info(self) -> AccountInfo:
        data = await self._get("/equity/account/info")
        return AccountInfo(**data)

    async def get_cash(self) -> CashInfo:
        data = await self._get("/equity/account/cash")
        return CashInfo(**data)

    # -------------------------------------------------------------------------
    # Portfolio / Positions
    # -------------------------------------------------------------------------

    async def get_positions(self) -> list[Position]:
        data = await self._get("/equity/portfolio")
        return [Position(**p) for p in (data if isinstance(data, list) else [])]

    async def get_position(self, ticker: str) -> Optional[Position]:
        try:
            data = await self._get(f"/equity/portfolio/{ticker}")
            return Position(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    # -------------------------------------------------------------------------
    # Orders
    # -------------------------------------------------------------------------

    async def get_orders(self) -> list[Order]:
        data = await self._get("/equity/orders")
        return [Order(**o) for o in (data if isinstance(data, list) else [])]

    async def place_market_order(self, req: MarketOrderRequest) -> Order:
        data = await self._post("/equity/orders/market", req.model_dump())
        return Order(**data)

    async def place_limit_order(self, req: LimitOrderRequest) -> Order:
        data = await self._post("/equity/orders/limit", req.model_dump())
        return Order(**data)

    async def place_stop_order(self, req: StopOrderRequest) -> Order:
        data = await self._post("/equity/orders/stop", req.model_dump())
        return Order(**data)

    async def cancel_order(self, order_id: int) -> dict:
        return await self._delete(f"/equity/orders/{order_id}")

    async def cancel_all_orders(self) -> list[dict]:
        return await self._delete("/equity/orders")

    # -------------------------------------------------------------------------
    # Instruments / metadata
    # -------------------------------------------------------------------------

    async def get_instruments(self) -> list[Instrument]:
        data = await self._get("/equity/metadata/instruments")
        return [Instrument(**i) for i in (data if isinstance(data, list) else [])]

    # -------------------------------------------------------------------------
    # Market data helpers
    # -------------------------------------------------------------------------

    async def get_price_history(
        self,
        ticker: str,
        period: str = "ONE_DAY",      # ONE_DAY, ONE_WEEK, ONE_MONTH, THREE_MONTHS, ONE_YEAR, ALL
        limit: int = 50,
    ) -> list[dict]:
        """Fetch OHLCV candles for a ticker (chart data endpoint)."""
        data = await self._get(
            f"/equity/history/orders/{ticker}",
            params={"limit": limit},
        )
        return data if isinstance(data, list) else []
