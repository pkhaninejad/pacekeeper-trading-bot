"""
FastAPI dashboard — serves REST API + SSE real-time feed + HTML UI.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api.client import Trading212Client
from src.api.models import BotStatus
from src.bot.engine import TradingEngine
from src.config.settings import settings

logger = logging.getLogger(__name__)

engine = TradingEngine()
_sse_clients: list[asyncio.Queue] = []

_cache: dict = {}
_CACHE_TTL = 30  # seconds


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and (datetime.utcnow() - entry["ts"]).seconds < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": datetime.utcnow()}


async def _broadcast(event: str, data: dict):
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    for q in list(_sse_clients):
        await q.put(msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(engine.start())
    yield
    engine.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Claude Trade Bot",
    description="Automated trading bot powered by Claude AI and Trading212",
    version="1.0.0",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="src/dashboard/templates")
templates.env.cache = None  # workaround for Jinja2 cache bug on Python 3.14


# ─── REST API ─────────────────────────────────────────────────────────────────

@app.get("/api/status", response_model=BotStatus, tags=["Bot"])
async def get_status():
    return engine.status


@app.post("/api/bot/toggle", tags=["Bot"])
async def toggle_bot():
    enabled = engine.toggle()
    await _broadcast("status", {"enabled": enabled})
    return {"enabled": enabled}


@app.get("/api/account", tags=["Account"])
async def get_account():
    cached = _cache_get("account")
    if cached:
        return cached
    try:
        async with Trading212Client() as client:
            info = await client.get_account_info()
            cash = await client.get_cash()
        result = {"info": info.model_dump(), "cash": cash.model_dump()}
        _cache_set("account", result)
        return result
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@app.get("/api/positions", tags=["Positions"])
async def get_positions():
    cached = _cache_get("positions")
    if cached:
        return cached
    try:
        async with Trading212Client() as client:
            positions = await client.get_positions()
        result = [p.model_dump() for p in positions]
        _cache_set("positions", result)
        return result
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@app.get("/api/orders", tags=["Orders"])
async def get_orders():
    try:
        async with Trading212Client() as client:
            orders = await client.get_orders()
        return [o.model_dump() for o in orders]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@app.delete("/api/orders/{order_id}", tags=["Orders"])
async def cancel_order(order_id: int):
    async with Trading212Client() as client:
        result = await client.cancel_order(order_id)
    return result


@app.get("/api/indicators", tags=["Market"])
async def get_indicators():
    """Return latest technical indicators for all watchlist tickers."""
    from src.bot.price_feed import get_price_summary
    data = get_price_summary(settings.WATCHLIST)
    result = {}
    for ticker, d in data.items():
        ind = d.get("indicators") or {}
        result[ticker] = {
            "price": d.get("current_price"),
            "change_pct_1d": d.get("change_pct_1d"),
            "summary": ind.get("summary", ""),
            "rsi": ind.get("rsi"),
            "macd": ind.get("macd", {}),
            "bollinger": ind.get("bollinger", {}),
            "ema": ind.get("ema", {}),
            "volume": ind.get("volume", {}),
        }
    return result


@app.get("/api/signals", tags=["Bot"])
async def get_signals():
    return [s.model_dump() for s in engine.signals_history]


@app.get("/api/trades", tags=["Bot"])
async def get_trade_log():
    return engine.trade_log


@app.post("/api/cycle", tags=["Bot"])
async def trigger_cycle():
    """Manually trigger a trading cycle."""
    asyncio.create_task(engine._cycle())
    return {"message": "Cycle triggered"}


@app.post("/api/positions/{ticker}/close", tags=["Positions"])
async def close_position(ticker: str):
    """Close a specific position by ticker."""
    from src.api.models import MarketOrderRequest
    async with Trading212Client() as client:
        pos = await client.get_position(ticker)
        if not pos:
            raise HTTPException(status_code=404, detail=f"No open position for {ticker}")
        qty = -pos.quantity
        order = await client.place_market_order(MarketOrderRequest(ticker=ticker, quantity=qty))
    _cache.pop("positions", None)
    return {"message": f"Closed {ticker}", "order_id": order.id}


@app.post("/api/positions/close-all", tags=["Positions"])
async def close_all_positions():
    """Close all open positions."""
    from src.api.models import MarketOrderRequest
    async with Trading212Client() as client:
        positions = await client.get_positions()
        results = []
        for pos in positions:
            try:
                qty = -pos.quantity
                order = await client.place_market_order(MarketOrderRequest(ticker=pos.ticker, quantity=qty))
                results.append({"ticker": pos.ticker, "order_id": order.id, "status": "closed"})
            except Exception as e:
                results.append({"ticker": pos.ticker, "status": "error", "detail": str(e)})
    _cache.pop("positions", None)
    return {"closed": results}


# ─── SSE real-time feed ───────────────────────────────────────────────────────

@app.get("/api/stream", tags=["Stream"])
async def sse_stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue()
    _sse_clients.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        # Send initial state
        yield f"event: status\ndata: {json.dumps(engine.status.model_dump(), default=str)}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _sse_clients.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Dashboard HTML ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")
