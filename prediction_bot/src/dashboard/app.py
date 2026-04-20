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
from fastapi.templating import Jinja2Templates

from prediction_bot.src.bot.engine import PredictionEngine

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


@app.get("/api/status")
async def get_status():
    return engine.status.model_dump(mode="json")


@app.post("/api/bot/toggle")
async def toggle_bot():
    enabled = engine.toggle()
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


@app.post("/api/cycle")
async def trigger_cycle():
    asyncio.create_task(engine._cycle())
    return {"status": "cycle triggered"}


@app.post("/api/interval")
async def set_interval(seconds: int):
    if seconds < 30:
        return {"error": "minimum interval is 30 seconds"}, 400
    engine.set_interval(seconds)
    return {"interval_seconds": seconds}


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
