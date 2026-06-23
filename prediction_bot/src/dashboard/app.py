"""FastAPI dashboard for the Prediction Market Bot."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from prediction_bot.src.bot.engine import PredictionEngine
from prediction_bot.src.dashboard.strategies_router import make_strategies_router

logger = logging.getLogger(__name__)

engine = PredictionEngine()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.cache = None  # workaround for Jinja2 cache bug on Python 3.14


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(engine.start())
    yield
    engine.stop()
    task.cancel()


app = FastAPI(title="Prediction Market Bot", lifespan=lifespan)

# In-memory mirror of which strategies are active (DB `active` column is the
# source of truth; the engine reads it each cycle via active_only=True).
_active_strategy_ids: set[str] = set()
app.include_router(
    make_strategies_router(engine._strategy_store, _active_strategy_ids),
    prefix="/api",
)

# Reuse the stock dashboard's shared static assets (strategy builder + tokens).
_SHARED_STATIC = Path(__file__).resolve().parents[3] / "src" / "dashboard" / "static"
app.mount("/static", StaticFiles(directory=str(_SHARED_STATIC)), name="static")


@app.get("/api/strategies/{strategy_id}/equity")
async def get_equity_curve(strategy_id: str):
    points = await engine._portfolio.equity_curve(strategy_id)
    return [{"timestamp": p.timestamp.isoformat(), "balance": p.balance} for p in points]


class ScannerSettingsUpdate(BaseModel):
    expiry_window_hours: int = Field(ge=1, le=24 * 365)
    min_liquidity: float = Field(ge=0.0)
    high_prob_min: float = Field(ge=0.0, le=1.0)
    high_prob_max: float = Field(ge=0.0, le=1.0)
    enabled_categories: list[str]


@app.get("/api/status")
async def get_status():
    return engine.status.model_dump(mode="json")


@app.post("/api/bot/toggle")
async def toggle_bot():
    enabled = engine.toggle()
    state = "enabled" if enabled else "paused"
    await engine._broadcast(
        {
            "type": "activity",
            "activity": {
                "timestamp": engine.activity_history[-1]["timestamp"] if engine.activity_history else None,
                "message": f"Bot {state} by user.",
            },
        }
    )
    return {"enabled": enabled}


@app.get("/api/stats")
async def get_stats():
    return await engine.paper_trader.store.get_stats()


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    trades = await engine.paper_trader.store.get_recent_trades(limit=limit)
    return [t.model_dump(mode="json") for t in trades]


@app.get("/api/trades/open")
async def get_open_trades():
    trades = await engine.paper_trader.store.get_open_trades()
    return [t.model_dump(mode="json") for t in trades]


@app.get("/api/bankroll-history")
async def get_bankroll_history():
    history = await engine.paper_trader.store.get_bankroll_history()
    return [s.model_dump(mode="json") for s in history]


@app.get("/api/scans")
async def get_scans():
    return list(reversed(engine.scan_history))


@app.get("/api/activity")
async def get_activity(limit: int = 20):
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100
    return list(reversed(engine.activity_history[-limit:]))


@app.post("/api/cycle")
async def trigger_cycle():
    asyncio.create_task(engine._cycle())
    return {"status": "cycle triggered"}


@app.post("/api/re-settle")
async def re_settle():
    corrected = await engine.paper_trader.re_settle_expired_trades(engine._clients)
    return {"corrected": corrected}


@app.post("/api/interval")
async def set_interval(seconds: int):
    if seconds < 30:
        return {"error": "minimum interval is 30 seconds"}, 400
    engine.set_interval(seconds)
    return {"interval_seconds": seconds}


@app.get("/api/settings")
async def get_settings():
    return {
        "expiry_window_hours": engine.settings.EXPIRY_WINDOW_HOURS,
        "min_liquidity": engine.settings.MIN_LIQUIDITY,
        "high_prob_min": engine.settings.HIGH_PROB_MIN,
        "high_prob_max": engine.settings.HIGH_PROB_MAX,
        "enabled_categories": engine.settings.ENABLED_CATEGORIES,
    }


@app.post("/api/settings")
async def update_settings(payload: ScannerSettingsUpdate):
    if payload.high_prob_min > payload.high_prob_max:
        return {"error": "high_prob_min cannot be greater than high_prob_max"}, 400
    cleaned_categories = [c.strip().lower() for c in payload.enabled_categories if c.strip()]
    if not cleaned_categories:
        return {"error": "at least one category is required"}, 400

    engine.settings.EXPIRY_WINDOW_HOURS = payload.expiry_window_hours
    engine.settings.MIN_LIQUIDITY = payload.min_liquidity
    engine.settings.HIGH_PROB_MIN = payload.high_prob_min
    engine.settings.HIGH_PROB_MAX = payload.high_prob_max
    engine.settings.ENABLED_CATEGORIES = cleaned_categories

    return {
        "updated": True,
        "settings": {
            "expiry_window_hours": engine.settings.EXPIRY_WINDOW_HOURS,
            "min_liquidity": engine.settings.MIN_LIQUIDITY,
            "high_prob_min": engine.settings.HIGH_PROB_MIN,
            "high_prob_max": engine.settings.HIGH_PROB_MAX,
            "enabled_categories": engine.settings.ENABLED_CATEGORIES,
        },
    }


@app.get("/api/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    engine._sse_queues.append(q)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            if q in engine._sse_queues:
                engine._sse_queues.remove(q)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "status": engine.status,
            "scan_history": list(reversed(engine.scan_history[:10])),
            "interval_seconds": engine.settings.SCAN_INTERVAL_SECONDS,
        },
    )
