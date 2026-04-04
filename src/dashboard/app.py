"""
FastAPI dashboard — serves REST API + SSE real-time feed + HTML UI.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

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
    async with Trading212Client() as client:
        info = await client.get_account_info()
        cash = await client.get_cash()
    return {"info": info.model_dump(), "cash": cash.model_dump()}


@app.get("/api/positions", tags=["Positions"])
async def get_positions():
    async with Trading212Client() as client:
        positions = await client.get_positions()
    return [p.model_dump() for p in positions]


@app.get("/api/orders", tags=["Orders"])
async def get_orders():
    async with Trading212Client() as client:
        orders = await client.get_orders()
    return [o.model_dump() for o in orders]


@app.delete("/api/orders/{order_id}", tags=["Orders"])
async def cancel_order(order_id: int):
    async with Trading212Client() as client:
        result = await client.cancel_order(order_id)
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
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
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
    return templates.TemplateResponse("dashboard.html", {"request": request})
